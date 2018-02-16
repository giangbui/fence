import authutils.errors
import authutils.token.keys
import authutils.token.validate
import flask
import jwt

from fence.jwt.blacklist import is_blacklisted
from fence.jwt.errors import JWTError, JWTPurposeError


def validate_purpose(claims, pur):
    """
    Check that the claims from a JWT have the expected purpose ``pur``

    Args:
        claims (dict): claims from token
        pur (str): expected purpose

    Return:
        None

    Raises:
        JWTPurposeError:
            if the claims do not contain a purpose claim or if it doesn't match
            the expected value
    """
    if 'pur' not in claims:
        raise JWTPurposeError('claims missing `pur` claim')
    if claims['pur'] != pur:
        raise JWTPurposeError(
            'claims have incorrect purpose: expected {}, got {}'
            .format(pur, claims['pur'])
        )


def validate_jwt(
        encoded_token=None, aud=None, purpose=None, public_key=None, **kwargs):
    """
    Validate a JWT and return the claims.

    This wraps the ``cdispyutils.auth`` functions to work correctly for fence
    and correctly validate the token. Other functions in fence should call this
    function and not use any functions from ``cdispyutils``.

    Args:
        encoded_token (str): the base64 encoding of the token
        aud (Optional[Iterable[str]]):
            list of audiences that the token must satisfy; defaults to
            ``{'openid'}`` (minimum expected by OpenID provider)
        purpose (Optional[str]):
            which purpose the token is supposed to be used for (access,
            refresh, or id)
        public_key (Optional[str]): public key to vaidate JWT with

    Return:
        dict: dictionary of claims from the validated JWT

    Raises:
        JWTError:
            if auth header is missing, decoding fails, or the JWT fails to
            satisfy any expectation
    """
    if encoded_token is None:
        try:
            encoded_token = (
                flask.request
                .headers['Authorization']
                .split(' ')[1]
            )
        except IndexError:
            raise JWTError('could not parse authorization header')
        except KeyError:
            raise JWTError('no authorization header provided')
    aud = aud or {'openid'}
    aud = set(aud)
    iss = flask.current_app.config['BASE_URL']
    issuers = [iss]
    oidc_iss = flask.current_app.config.get('OIDC_ISSUER')
    if oidc_iss:
        issuers.append(oidc_iss)
    try:
        token_headers = jwt.get_unverified_header(encoded_token)
    except jwt.exceptions.InvalidTokenError as e:
        raise JWTError('Invalid token : {}'.format(str(e)))
    token_iss = jwt.decode(encoded_token, verify=False).get('iss')

    public_key = authutils.token.keys.get_public_key(
        token_headers.get('kid'), token_iss, attempt_refresh=(token_iss != iss)
    )
    try:
        claims = authutils.token.validate.validate_jwt(
            encoded_token=encoded_token,
            aud=aud,
            purpose=purpose,
            issuers=issuers,
            public_key=public_key,
            **kwargs
        )
    except authutils.errors.JWTError as e:
        msg = 'Invalid token : {}'.format(str(e))
        unverified_claims = jwt.decode(claims, verify=False)
        if '' in unverified_claims['aud']:
            msg += '; was OIDC client configured with scopes?'
        raise JWTError(msg)
    if purpose:
        validate_purpose(claims, purpose)
    if 'pur' not in claims:
        raise JWTError(
            'token {} missing purpose (`pur`) claim'
            .format(claims['jti'])
        )

    # For refresh tokens and API keys specifically, check that they are not
    # blacklisted.
    if claims['pur'] == 'refresh' or claims['pur'] == 'api_key':
        if is_blacklisted(claims['jti']):
            raise JWTError('token is blacklisted')

    return claims


def require_jwt(aud=None, purpose=None):

    def decorator(f):

        def wrapper(*args, **kwargs):

            validate_jwt(aud=aud, purpose=purpose)
            return f(args, kwargs)

        return wrapper

    return decorator
