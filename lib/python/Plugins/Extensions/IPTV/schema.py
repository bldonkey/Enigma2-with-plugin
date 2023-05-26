# Embedded file name: src/schema.py

from datetime import datetime
try:
    from typing import Type, Any, TypeVar, TYPE_CHECKING, Dict, List, Optional
    _T = TypeVar('_T')
    _I = TypeVar('_I', str, int)
    _O = TypeVar('_O', bound='ObjectData')
    _F = TypeVar('_F', bound='Field')
except ImportError:
    TYPE_CHECKING = False

class Field(object):
    default = None

    def fromJson(self, value):
        raise NotImplementedError()

    def toJson(self, value):
        raise NotImplementedError()

    @staticmethod
    def _assert_type(ty, value):
        if type(value) is not ty:
            raise ValueError('Bad value type %s, expected %s' % (type(value), ty))


class StringField(Field):

    def __init__(self, default = ''):
        self.default = default

    def fromJson(self, value):
        if type(value) is not str:
            raise ValueError('Expected unicode string - got %s' % type(value))
        return value.encode('utf-8')

    def toJson(self, value):
        return value


def tstr(default = ''):
    return StringField(default=default)


class IntField(Field):

    def __init__(self, default):
        self.default = default

    def fromJson(self, value):
        if type(value) is not int:
            raise ValueError('Expected int - got %s' % type(value))
        return value

    def toJson(self, value):
        return value


def tint(default = 0):
    return IntField(default)


class BoolField(Field):

    def __init__(self):
        self.default = False

    def fromJson(self, value):
        if type(value) is bool:
            return value
        if type(value) is int:
            return value == 0
        raise ValueError('Expected bool or int - got %s' % type(value))

    def toJson(self, value):
        return value


def tbool():
    return BoolField()


class DateTimeField(Field):

    def __init__(self):
        self.default = datetime.fromtimestamp(0)

    def fromJson(self, value):
        if type(value) is int or type(value) is str:
            return datetime.fromtimestamp(int(value))
        raise ValueError('Invalid type %s' % type(value))

    def toJson(self, value):
        return int(value.strftime('%s'))


def tdatetime():
    return DateTimeField()


class ChoicesField(Field):

    def __init__(self, choices):
        self.choices = choices
        self.default = self.getByIndex(0)

    def fromJson(self, value):
        if not (type(value) == str or type(value) == int):
            raise ValueError('Bad value type %s' % type(value))
        if value not in self.choices:
            raise ValueError('Bad value %s' % value)
        return value

    def toJson(self, value):
        return value

    def getByIndex(self, index):
        return self.choices[index]

    def getChoices(self):
        raise NotImplementedError()


def tchoices(choices):
    return ChoicesField(choices)


class ListField(Field):
    default = []

    def __init__(self, item):
        self.item = item

    def fromJson(self, value):
        self._assert_type(list, value)
        return [ self.item.fromJson(x) for x in value ]

    def toJson(self, value):
        return [ self.item.toJson(x) for x in value ]


def tlist(item):
    return ListField(item)


class TupleField(Field):

    def __init__(self, items):
        self.items = items
        self.default = tuple((item.default for item in items))

    def fromJson(self, value):
        self._assert_type(list, value)
        return tuple((item.fromJson(value[i]) for i, item in enumerate(self.items)))

    def toJson(self, value):
        return [ self.items[i].toJson(v) for i, v in enumerate(value) ]


def ttuple(items):
    return TupleField(items)


class DictField(Field):
    default = {}

    def __init__(self, key, value):
        self._key = key
        self._value = value

    def fromJson(self, value):
        self._assert_type(dict, value)
        return {self._key.fromJson(k):self._value.fromJson(v) for k, v in list(value.items())}

    def toJson(self, value):
        return {self._key.toJson(k):self._value.toJson(v) for k, v in list(value.items())}


def tdict(key, value):
    return DictField(key, value)


class OptionalField(Field):

    def __init__(self, data):
        self.data = data

    def fromJson(self, value):
        if value is None:
            return
        else:
            return self.data.fromJson(value)

    def toJson(self, value):
        return value and self.data.toJson(value)


def toptional(item):
    return OptionalField(item)


class ObjectMeta(type):

    def __new__(cls, name, bases, namespace):
        fields = {}
        for base in reversed(bases):
            if hasattr(base, '_schema'):
                fields.update(getattr(base, '_schema'))

        for name, value in list(namespace.items()):
            if isinstance(value, Field):
                fields[name] = value

        namespace['_schema'] = fields
        for k in fields:
            if k in namespace:
                del namespace[k]

        return super(ObjectMeta, cls).__new__(cls, name, bases, namespace)


class ObjectData(Field, metaclass=ObjectMeta):
    if TYPE_CHECKING:
        _schema = {}

    def __init__(self, **kvargs):
        for k, sc in list(self._schema.items()):
            setattr(self, k, kvargs.get(k, sc.default))

    @classmethod
    def fromJson(cls, value):
        cls._assert_type(dict, value)
        obj = cls.__new__(cls)
        for k, sc in list(cls._schema.items()):
            try:
                v = value[k]
            except KeyError:
                raise ValueError('missing key %s' % k)

            setattr(obj, k, sc.fromJson(v))

        return obj

    @classmethod
    def toJson(cls, value):
        obj = {}
        for k, sc in list(cls._schema.items()):
            obj[k] = sc.toJson(getattr(value, k))

        return obj

    @classmethod
    def default(cls):
        return cls()

    def dump(self):
        return self.toJson(self)


class AttrField(Field):

    def __init__(self, attr_type):
        self._type = attr_type
        import types
        if hasattr(self._type, 'default') and isinstance(self._type.default, types.MethodType):
            self.default = self._type.default()

    def fromJson(self, value):
        return self._type.fromJson(value)

    def toJson(self, value):
        return self._type.toJson(value)


def tattr(attr_type):
    return AttrField(attr_type)