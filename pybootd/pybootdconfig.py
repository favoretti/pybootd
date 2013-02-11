import sys
import os

try:
    import yaml
except:
    print "Please install yaml module"
    sys.exit(1)

LOGGER_TYPE = 'stderr'
LOGGER_LEVEL = 'info'

BOOTP_PORT = 67
BOOTP_DEFAULT_BOOT_FILE = '\x00'
BOOTP_DEFAULT_LEASE_TIME = 7200
BOOTP_DEFAULT_DNS = 'auto'

TFTP_BLOCKSIZE = 512
TFTP_TIMEOUT = 2.0
TFTP_PORT = 69

class PyBootdConfig(object):

    def __init__(self, config_file):
        try:
            self.enable_bootp = True
            self.enable_tftp = True
            self.__config = yaml.load(open(config_file, 'r').read())
            print("Configuration loaded from {config}.".format(config=config_file))
            self.__validate_config()
        except Exception, err:
            print("Failed to parse or validate configuration file!\n{err}".format(err=err))
            sys.exit(1)

    def __section_exists(self, section):
        if not section in self.__config.keys():
            return False
        else:
            return True

    def __key_exists(self, section, key):
        if not section or not key:
            return False

        if not self.__section_exists(section):
            return False

        if not key in self.__config[section].keys():
            return False

        return True

    def __validate_config(self):
        if not self.__section_exists("logger"):
            print("INFO: logger settings aren't defined, using defaults.")
            self.__config['logger'] = { 'type' : LOGGER_TYPE, 'level' : LOGGER_LEVEL }
        else:
            if not self.__key_exists('logger', 'type'):
                self.__config['logger']['type'] = LOGGER_TYPE

            if not self.__key_exists('logger', 'level'):
                self.__config['logger']['level'] = LOGGER_LEVEL

        if not self.__section_exists("bootp"):
            print("WARNING: no bootp configuration found, bootp listener won't be started!")
            self.enable_bootp = False
        else:
            if not self.__key_exists('bootp', 'bind_interface'):
                print("ERROR: 'bootp' parameter 'bind_interface' is not defined, can't start bootp!")
                sys.exit(1)

        if not self.__section_exists("tftp"):
            print("WARNING: no tftp configuration found, tftp listener won't be started!")
            self.enable_tftp = False
        else:
            if not self.__key_exists('tftp', 'bind_interface'):
                print("ERROR: 'tftp' parameter 'bind_interface' is not defined, can't start tftp!")
                sys.exit(1)

    def get_logger_type(self):
        return self.__config['logger']['type']

    def get_logger_file(self):
        if 'file' in self.__config['logger'].keys():
            return self.__config['logger']['file']
        else:
            return None

    def get_logger_level(self):
        return self.__config['logger']['level']

    def get_bootp_bind_interface(self):
        return self.__config['bootp']['bind_interface']

    def get_bootp_port(self):
        if self.__key_exists('bootp', 'port'):
            return self.__config['bootp']['port']
        else:
            return BOOTP_PORT

    def get_bootp_acl_type(self):
        if self.__key_exists('bootp', 'acl'):
            return self.__config['bootp']['acl']
        else:
            return None

    def get_bootp_default_boot_file(self):
        if self.__key_exists('bootp', 'default_boot_file'):
            return self.__config['bootp']['default_boot_file']
        else:
            return BOOTP_DEFAULT_BOOT_FILE

    def get_bootp_default_lease_time(self):
        if self.__key_exists('bootp', 'default_lease_time'):
            return self.__config['bootp']['default_lease_time']
        else:
            return BOOTP_DEFAULT_LEASE_TIME

    def get_bootp_default_dns(self):
        if self.__key_exists('bootp', 'default_dns'):
            return self.__config['bootp']['default_dns']
        else:
            return BOOTP_DEFAULT_DNS

    def get_bootp_allow_simple_dhcp(self):
        if self.__key_exists('bootp', 'allow_simple_dhcp'):
            return self.__config['bootp']['allow_simple_dhcp']
        else:
            return None


    def get_tftp_bind_interface(self):
        return self.__config['tftp']['bind_interface']

    def get_tftp_blocksize(self):
        if self.__key_exists('tftp', 'blocksize'):
            return self.__config['tftp']['blocksize']
        else:
            return TFTP_BLOCKSIZE

    def get_tftp_timeout(self):
        if self.__key_exists('tftp', 'timeout'):
            return self.__config['tftp']['timeout']
        else:
            return TFTP_TIMEOUT

    def get_tftp_port(self):
        if self.__key_exists('tftp', 'port'):
            return self.__config['tftp']['port']
        else:
            return TFTP_PORT

    def get_tftp_root(self):
        if self.__key_exists('tftp', 'root'):
            return self.__config['tftp']['root']
        else:
            return os.getcwd()

    def get_leases(self):
        if not self.__section_exists('bootp_leases'):
            return {}
        else:
            return self.__config['bootp_leases']

    def get_lease_for_mac(self, mac):
        if not mac or not mac in self.get_leases().keys():
            return None

        return self.get_leases()[mac]

