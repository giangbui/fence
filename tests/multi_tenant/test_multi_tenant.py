"""
It is very recommended to look at the multi-tenant flow diagram before looking
at this code; otherwise it is likely for none of this to make any sense.
"""

import urllib
import urlparse
# in python3:
# urllib.parse

import requests

import fence

from tests.utils import oauth2
from tests.utils import remove_qs


def test_redirect_from_oauth(fence_client_app, oauth_client):
    """
    Test that the ``/oauth2/authorize`` endpoint on the client redirects to the
    ``/login/fence`` endpoint, also on the client.
    """
    with fence_client_app.test_client() as client:
        data = {
            'client_id': oauth_client.client_id,
            'redirect_uri': oauth_client.url,
            'response_type': 'code',
            'scope': 'openid user',
            'state': fence.utils.random_str(10),
            'confirm': 'yes',
        }
        response_oauth_authorize = client.post('/oauth2/authorize', data=data)
        assert response_oauth_authorize.status_code == 302
        assert '/login/fence' in response_oauth_authorize.location


def test_login(
        fence_client_app, fence_oauth_client, fence_oauth_client_url,
        fence_idp_server, mock_get, example_keys_response, monkeypatch):
    """
    Test that:
        - the ``/login/fence`` client endpoint redirects to the
          ``/oauth2/authorize`` endpoint on the IDP fence,
    """
    monkeypatch.setattr(
        'authutils.token.keys.refresh_jwt_public_keys',
        lambda: None
    )
    with fence_client_app.test_client() as client:
        redirect_url_quote = urllib.quote('/login/fence/login')
        path = '/login/fence?redirect_uri={}'.format(redirect_url_quote)
        response_login_fence = client.get(path)
        # This should be pointing at ``/oauth2/authorize`` of the IDP fence.
        assert '/oauth2/authorize' in response_login_fence.location
        # Remove the QS from the URL so we can use POST instead.
        url = remove_qs(response_login_fence.location)
        # should now have ``url == 'http://localhost:50000/oauth2/authorize``.
        # de-listify the QS arguments
        authorize_params = urlparse.parse_qs(
            urlparse.urlparse(response_login_fence.location).query
        )
        authorize_params = {k: v[0] for k, v in authorize_params.iteritems()}
        authorize_params['confirm'] = 'yes'
        headers = oauth2.create_basic_header_for_client(fence_oauth_client)
        authorize_response = requests.post(
            url, headers=headers, data=authorize_params, allow_redirects=False
        )
        assert authorize_response.status_code == 302
        assert 'Location' in authorize_response.headers
        authorize_redirect = authorize_response.headers['Location']
        assert remove_qs(authorize_redirect) == fence_oauth_client_url
        assert 'code' in authorize_redirect
