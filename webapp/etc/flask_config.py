class Config(object):
    """ Global configuration """
    PORT = "2005"
    DEBUG = False
    TESTING = False


class ProductionConfig(Config):
    """ Additional configuration for production system """
    def __init__(self) -> None:
        print('Production configuration')
    pass


class DevelopmentConfig(Config):
    """ Additional configuration for development system """
    def __init__(self) -> None:
        print('Development configuration')
    PORT = "2005"
    DEBUG = True
    HOST = "0.0.0.0"


class TestingConfig(Config):
    """ Additional configuration for test system """
    def __init__(self) -> None:
        print('Test configuration')
    TESTING = True
