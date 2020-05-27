from collections import UserDict


class Registry(UserDict):

    def __init__(self, required):
        if not isinstance(required, type):
            raise TypeError(f"{required} is not a class")
        self.required = required
        super().__init__()

    def __call__(self, factory):
        if isinstance(factory, type):
            # Class based
            name = getattr(factory, 'name', factory.__name__.lower())
        else:
            # Object based
            name = factory.name
        self[name] = factory
        return factory

    def __setitem__(self, key:str, factory):
        if isinstance(factory, type):
            # Class based factory
            if not issubclass(factory, self.required):
                raise TypeError(f"{factory} isn't any of the required: {self.required}")
            abs_methods = getattr(factory, '__abstractmethods__', None)
            if abs_methods:
                missing = "', '".join(abs_methods)
                raise TypeError(f"{factory} doesn't implement the required abstract methods: '{missing}'")
        else:
            # Object based
            if not isinstance(factory, self.required):
                raise TypeError(f"{factory} isn't an instance of the required: {self.required}")
        super().__setitem__(key, factory)
