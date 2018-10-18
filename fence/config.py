import os
from collections import Mapping
import glob
from yaml import safe_load as yaml_load
from yaml.scanner import ScannerError
import urlparse

import cirrus
from jinja2 import Template


from fence.settings import CONFIG_SEARCH_FOLDERS

from logging import getLogger

logger = getLogger(__name__)


class Config(Mapping):
    """
    Configuration singleton that's instantiated on module load.
    Allows updating from a config file by using .update()
    """

    def __init__(self):
        self._configs = {}

    def get(self, key, *args):
        return self._configs.get(key, *args)

    def set(self, key, value):
        self._configs.__setitem__(key, value)

    def __setitem__(self, key, value):
        self._configs.__setitem__(key, value)

    def __contains__(self, key):
        return key in self._configs

    def __iter__(self):
        for key, value in self._configs.iteritems():
            yield key, value

    def __getitem__(self, key):
        return self._configs[key]

    def __delitem__(self, key):
        del self._configs[key]

    def __len__(self):
        return len(self._configs)

    def __str__(self):
        return str(self._configs)

    def update(self, *args, **kwargs):
        """
        update configuration properties
        """
        self._configs.update(*args)
        self._configs.update(kwargs)

    def load(self, config_path=None, file_name=None):
        # TODO remove try, except when local_settings.py is no longer supported
        try:
            config_path = config_path or get_config_path(
                CONFIG_SEARCH_FOLDERS, file_name
            )
        except IOError:
            # TODO local_settings.py is being deprecated. Fow now, support
            # not proving a yaml configuration but log a warning.
            logger.warning(
                "No YAML configuration found. Will attempt "
                "to run without. If still using deprecated local_settings.py, you "
                "can ignore this warning but PLEASE upgrade to using the newest "
                "configuration format. local_settings.py is DEPRECATED!!"
            )
            config_path = None

        if config_path:
            self._load_configuration_file(config_path)

        self._post_process()

    def _load_configuration_file(self, provided_config_path):
        logger.info("Loading default configuration...")
        config = yaml_load(
            open(
                os.path.join(
                    os.path.dirname(os.path.abspath(__file__)), "config-default.yaml"
                )
            )
        )

        logger.info("Loading configuration: {}".format(provided_config_path))

        # treat cfg as template and replace vars, returning an updated dict
        provided_configurations = nested_render(
            yaml_load(open(provided_config_path)), {}, {}
        )

        # only update known configuration values. In the situation
        # where the provided config does not have a certain value,
        # the default will be used.
        common_keys = {
            key: value
            for (key, value) in config.iteritems()
            if key in provided_configurations
        }
        keys_to_update = {
            key: value
            for (key, value) in provided_configurations.iteritems()
            if key in common_keys
        }
        unknown_keys = {
            key: value
            for (key, value) in provided_configurations.iteritems()
            if key not in common_keys
        }

        config.update(keys_to_update)

        if unknown_keys:
            logger.warning(
                "Unknown key(s) {} found in {}. Will be ignored.".format(
                    unknown_keys.keys(), provided_config_path
                )
            )

        self._configs.update(config)

        import pprint

        pprint.pprint(self._configs)

    def _post_process(self):
        """
        Do some post processing to the configuration (set env vars if necessary,
        do more complex modifications/changes to vars, etc.)

        Called after loading the configuration and doing the template-replace.
        """
        pass


def nested_render(cfg, fully_rendered_cfgs, replacements):
    """
    Template render the provided cfg by recurisevly replacing {{var}}'s which values
    from the current "namespace".

    The nested config is treated like nested namespaces where the inner variables
    are only available in current block and further nested blocks.

    Said the opposite way: the namespace with available vars that can be used
    includes the current block's vars and parent block vars.

    This means that you can do replacements for top-level
    (global namespaced) config vars anywhere, but you can only use inner configs within
    that block or further nested blocks.

    An example is worth a thousand words:

        ---------------------------------------------------------------------------------
        fence-config.yaml
        --------------------------------------------------------------------------------
        BASE_URL: 'http://localhost/user'
        OPENID_CONNECT:
          fence:
            api_base_url: 'http://other_fence/user'
            client_kwargs:
              redirect_uri: '{{BASE_URL}}/login/fence/login'
            authorize_url: '{{api_base_url}}/oauth2/authorize'
        THIS_WONT_WORK: '{{api_base_url}}/test'
        --------------------------------------------------------------------------------

    "redirect_uri" will become "http://localhost/user/login/fence/login"
        - BASE_URL is in the global namespace so it can be used in this nested cfg

    "authorize_url" will become "http://other_fence/user/oauth2/authorize"
        - api_base_url is in the current namespace, so it is available

    "THIS_WONT_WORK" will become "/test"
        - Why? api_base_url is not in the current namespace and so we cannot use that
          as a replacement. the configuration (instead of failing) will replace with
          an empty string

    Args:
        cfg (TYPE): Description
        fully_rendered_cfgs (TYPE): Description
        replacements (TYPE): Description

    Returns:
        dict: Configurations with template vars replaced
    """
    try:
        for key, value in cfg.iteritems():
            replacements.update(cfg)
            fully_rendered_cfgs[key] = {}
            fully_rendered_cfgs[key] = nested_render(
                value,
                fully_rendered_cfgs=fully_rendered_cfgs[key],
                replacements=replacements,
            )
            # new namespace, remove current vars (no longer available as replacements)
            for old_cfg, value in cfg.iteritems():
                replacements.pop(old_cfg, None)

        return fully_rendered_cfgs
    except AttributeError:
        # it's not a dict, so lets try to render it. But only if it's
        # truthy (which means there's actually something to replace)
        if cfg:
            t = Template(str(cfg))
            rendered_value = t.render(**replacements)
            try:
                cfg = yaml_load(rendered_value)
            except ScannerError:
                # it's not loading into yaml, so let's assume it's a string with special
                # chars such as: {}[],&*#?|:-<>=!%@\)
                #
                # in YAML, we have to "quote" a string with special chars.
                #
                # since yaml_load isn't loading from a file, we need to wrap the Python
                # str in actual quotes.
                cfg = yaml_load('"{}"'.format(rendered_value))

        return cfg


def get_config_path(search_folders, file_name="*config.yaml"):
    """
    Return the path of a single configuration file ending in config.yaml
    from one of the search folders.

    NOTE: Will return the first match it finds. If multiple are found,
    this will error out.
    """
    possible_configs = []
    for folder in search_folders:
        config_path = os.path.join(folder, file_name)
        possible_files = glob.glob(config_path)
        possible_configs.extend(possible_files)

    if len(possible_configs) == 1:
        return possible_configs[0]
    elif len(possible_configs) > 1:
        raise IOError(
            "Multiple config.yaml files found: {}. Please specify which "
            'configuration to use with "python run.py -c some-config.yaml".'.format(
                str(possible_configs)
            )
        )
    else:
        raise IOError(
            "Could not find config.yaml. Searched in the following locations: "
            "{}".format(str(search_folders))
        )


class FenceConfig(Config):
    def __init__(self, *args, **kwargs):
        super(FenceConfig, self).__init__(*args, **kwargs)

    def _post_process(self):
        if "ROOT_URL" not in self._configs:
            url = urlparse.urlparse(self._configs["BASE_URL"])
            self._configs["ROOT_URL"] = "{}://{}".format(url.scheme, url.netloc)

        # allow authlib traffic on http for development if enabled. By default
        # it requires https.
        #
        # NOTE: use when fence will be deployed in such a way that fence will
        #       only receive traffic from internal clients, and can safely use HTTP
        if self._configs.get("AUTHLIB_INSECURE_TRANSPORT"):
            os.environ["AUTHLIB_INSECURE_TRANSPORT"] = "true"

        # if we're mocking storage, ignore the storage backends provided
        # since they'll cause errors if misconfigured
        if self._configs.get("MOCK_STORAGE", False):
            self._configs["STORAGE_CREDENTIALS"] = {}

        cirrus.config.config.update(**self._configs.get("CIRRUS_CFG", {}))


config = FenceConfig()
