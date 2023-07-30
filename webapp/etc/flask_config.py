class Config(object):
    """ Global configuration """
    PORT = "5000"
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
    PORT = "5001"
    DEBUG = True


class TestingConfig(Config):
    """ Additional configuration for test system """
    def __init__(self) -> None:
        print('Test configuration')
    TESTING = True