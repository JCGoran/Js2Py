'''Most important file in Js2Py implementation: PyJs class - father of all PyJs objects'''
from copy import copy
from utils.injector import fix_js_args
from translators.jsparser import OP_METHODS
from types import FunctionType
import traceback
__all__ = ['Js', 'PyJsComma', 'PyJsStrictEq', 'PyJsStrictNeq',
           'PyJsException', 'PyJsBshift', 'Scope', 'PyExceptionToJs',
           'JsToPyException', 'JS_BUILTINS']


def Js(val):
    '''Converts Py type to PyJs type'''
    if isinstance(val, PyJs):
        return val
    elif val is None:
        return undefined
    elif isinstance(val, basestring):
        return PyJsString(val, StringPrototype)
    elif isinstance(val, bool):
        return true if val else false
    elif isinstance(val, float) or isinstance(val, int) or isinstance(val, long):
        return PyJsNumber(float(val), NumberPrototype)
    elif isinstance(val, tuple): # convert to arguments
        return val # todo later
    elif isinstance(val, FunctionType):
        return PyJsFunction(val, FunctionPrototype)
    elif isinstance(val, dict): # convert to object
         temp = PyJsObject({}, ObjectPrototype)
         for k, v in val.iteritems():
             temp.put(k, v)
         return temp
    elif isinstance(val, list): #Convert to array
        return PyJsArray(val, ArrayPrototype)
    else:
        raise RuntimeError('Cant convert python type to js')

def Type(val):
    if isinstance(val, PyJsObject):
        return 'Object'
    elif isinstance(val, PyJsNumber):
        return 'Number'
    elif isinstance(val, PyJsString):
        return 'String'
    elif isinstance(val, PyJsBoolean):
        return 'Boolean'
    elif isinstance(val, PyJsNull):
        return 'Null'
    elif isinstance(val, PyJsUndefined):
        return 'Undefined'
    elif isinstance(val, PyJs):
        return 'Object'
    raise RuntimeError('Invalid type: '+str(val))

def is_data_descriptor(desc):
    return desc and ('value' in desc or 'writable' in desc)
    
def is_accessor_descriptor(desc):
    return desc and ('get' in desc or 'set' in desc)
    
def is_generic_descriptor(desc):
    return desc and not (is_data_descriptor(desc) or is_accessor_descriptor(desc))


this = globals()  # this should be a global object...

##############################################################################

class PyJs:
    PRIMITIVES =  {'String', 'Number', 'Boolean', 'Undefined', 'Null'}
    Class = None
    extensible = True
    prototype = None
    own = {}
    value = None
    
    def __init__(self, value=None, prototype=None, extensible=False):
        '''Constructor for Number String and Boolean'''
        if self.Class=='String' and not isinstance(value, basestring):
            raise TypeError
        if self.Class=='Number':
            if not isinstance(value, float):
                if not (isinstance(value, int) or isinstance(value, long)):
                    raise TypeError
                value = float(value)
        if self.Class=='Boolean' and not isinstance(value, bool):
            raise TypeError
        self.value = value
        self.extensible = extensible
        self.prototype = prototype
        self.own = {}
        
    def is_undefined(self):
        return self.Class=='Undefined'
    
    def is_null(self):
        return self.Class=='Null'
        
    def is_primitive(self):
        return self.Class in self.PRIMITIVES
    
    def is_object(self):
        return not self.is_primitive()
    
    def is_callable(self):
        return not self.is_primitive() and hasattr(self, 'call')
        
    def typ(self):
        """This one checks CLASS property not the instance type
           So for example (new Number(2)).typ() would give Number but Type(new Number(2)) gives Object
           Stupid javascript makes no sense."""
        typ = self.Class
        if self.is_primitive():
            return typ
        return 'Object'
    
    def get_own_property(self, prop):
        return self.own.get(prop)
    
    def get_property(self, prop):
        cand = self.get_own_property(prop)
        if cand:
            return cand
        if self.prototype is not None:
            return self.prototype.get_property(prop)
    
    def get(self, prop): #external use!
         #prop = prop.value
         if self.Class=='Undefined' or self.Class=='Null':
             raise TypeError('Undefiend and null dont have properties!')
         if not isinstance(prop, basestring):
             prop = prop.to_string().value
         if not isinstance(prop, basestring): raise RuntimeError('Bug')
         cand = self.get_property(prop)
         if cand is None:
             return Js(None)
         if is_data_descriptor(cand): 
             return cand['value']
         if cand['get'].is_undefined():
             return cand['get']
         return cand['get'].call(self)
    
    def can_put(self, prop):  #to check
        desc = self.get_own_property(prop)
        if desc: #if we have this property
            if is_accessor_descriptor(desc):
                return desc['set'].is_callable() # Check if setter method is defined           
            else:  #data desc 
                return desc['writable']
        if self.prototype is not None:
            return self.extensible
        inherited = self.get_property(prop)
        if inherited is None:
            return self.extensible
        if is_accessor_descriptor(inherited):
            return not inherited['set'].is_undefined()
        elif self.extensible:
            return inherited['writable']
        return False
            
    
    def put(self, prop, val, op=None):  #external use!
        '''Just like in js: self.prop op= val
           for example when op is '+' it will be self.prop+=val
           op can be either None for simple assignment or one of:
           * / % + - << >> & ^ |'''
        if self.Class=='Undefined' or self.Class=='Null':
             raise TypeError('Undefiend and null dont have properties!')
        if not isinstance(prop, basestring):
             prop = prop.to_string().value
        if not isinstance(prop, basestring): raise RuntimeError('Bug')
        #we need to set the value to the incremented one
        if op is not None:
            val = getattr(self.get(prop), OP_METHODS[op])(val)
        if not self.can_put(prop):
            return val 
        own_desc = self.get_own_property(prop)
        if is_data_descriptor(own_desc):
            own_desc['value'] = val
            return val
        desc = self.get_property(prop)
        if is_accessor_descriptor(desc):
            desc['set'].call(self, val)
        else:
            self.own[prop] = {'value' : val, 
                              'writable' : True,
                              'configurable' : True,
                              'enumerable' : True}
        return val
                
    def has_property(self, prop):
        return self.get_property(prop) is not None
    
    def delete(self, prop):
        desc = self.get_own_property(prop)
        if desc is None: 
            return Js(True)
        if desc['configurable']:
            del self.own[prop]
            return Js(True)
        return Js(False)
    
    def default_value(self, hint=None):
        order = ['toString', 'valueOf']
        if hint=='Number' or (hint is None and self.Class=='Date'):
            order.reverse()
        for meth_name in order:
            method = self.get(meth_name)
            if method is not None and method.is_callable():
                cand = method.call(self)
                if cand.is_primitive():
                    return cand
        raise TypeError('Cannot convert object to primitive value')
        
    def define_own_property(self, prop, desc): #Internal use only. External through Object
        #Messy method -  raw translation from Ecma spec to prevent any bugs.
        current = self.get_own_property(prop)
        
        extensible = self.extensible
        default_data_desc = {'value': undefined, #undefined
                             'writable': False, 
                             'enumerable': False,
                             'configurable': False}
        default_accessor_desc = {'get': undefined, #undefined
                                 'set': undefined, #undefined
                                 'enumerable': False,
                                 'configurable': False}
        if not current: #We are creating a new property
            if not extensible:
                return False
            if is_data_descriptor(desc) or is_generic_descriptor(desc):
                default_data_desc.update(desc)
                self.own[prop] = default_data_desc
            else:
                default_accessor_desc.update(desc)
                self.own[prop] = default_accessor_desc
            return True
        
        if not desc or desc==current: #We dont need to change anything.
            return True
        configurable = current['configurable']  
        if not configurable:  #Prevent changing configurable or enumerable
            if desc['configurable']:
                return False
            if desc['enumerable']!=current['enumerable']:
                return False
        if is_generic_descriptor(desc):
            pass
        elif is_data_descriptor(current)!=is_data_descriptor(desc):
            if not configurable:
                return False
            if is_data_descriptor(current):
                del current['value']
                del current['writable']
                current['set'] = undefined #undefined
                current['get'] = undefined #undefined
            else:
                del current['set']
                del current['get']
                current['value'] = undefined #undefined
                current['writable'] = False 
        elif is_data_descriptor(current) and is_data_descriptor(desc):
            if not configurable:
                if not current['writable'] and desc['writable']:
                    return False
            if not current['writable'] and 'value' in desc and current['value']!=desc['value']:
                return False
        elif is_accessor_descriptor(current) and is_accessor_descriptor(desc):
            if not configurable:
                if 'set' in desc and desc['set'] is not current['set']:
                    return False
                if 'get' in desc and desc['get'] is not current['get']:
                    return False
        current.update(desc)
        return True
    
    #Type Conversions. to_type. All must return pyjs subclass instance
    
    def to_primitive(self, hint=None):
        if self.is_primitive():
            return self
        return self.default_value(hint)
            
    def to_boolean(self):
        typ = self.Class
        if typ=='Boolean': #no need to convert
            return self
        elif typ=='Null' or typ=='Undefined': #they are both allways false
            return false
        elif typ=='Number' or typ=='String': #false only for 0, '' and NaN
            return Js(bool(self.value and self.value==self.value)) # test for nan (nan -> flase)
        else: #object -  allways true
            return true
            
    def to_number(self):
        typ = self.Class
        if typ=='Null':  #null is 0
            return Js(0)
        elif typ=='Undefined':  # undefined is NaN
            return NaN
        elif typ=='Boolean':    # 1 for true 0 for false
            return Js(int(self.value))
        elif typ=='Number':   # no need to convert
            return self
        elif typ=='String':
            s = self.value.strip() #Strip white space
            if not s: # '' is simply 0
                return Js(0)
            if 'x' in s or 'X' in s: #hex (positive only)
                try: # try to convert
                    num = int(s, 16)
                except ValueError: # could not convert > NaN
                    return NaN
                return num
            sign = 1 #get sign
            if s[0] in '+-':
                if s[0]=='-': 
                    sign = -1
                s = s[1:]
            if s=='Infinity': #Check for infinity keyword. 'NaN' will be NaN anyway.
                return Js(sign*float('inf'))
            try: #decimal try
                num = sign*float(s) # Converted
            except ValueError:
                return NaN # could not convert to decimal  > return NaN
            return Js(num) 
        else: #object -  most likely it will be NaN.
            return self.to_primitive('Number').to_number()
            
    def to_string(self):
        typ = self.Class
        if typ=='Null':
            return Js('null')
        elif typ=='Undefined':
            return Js('undefined')
        elif typ=='Boolean':
            return Js('true') if self.value else Js('false')
        elif typ=='Number':
            if self.is_nan():
                return Js('NaN')
            elif self.is_infinity():
                sign = '-' if self.value<0 else ''
                return Js(sign+'Infinity')
            elif self.value.is_integer():  # dont print .0 
                return Js(str(int(self.value)))
            return Js(str(self.value)) # accurate enough
        elif typ=='String':
            return self
        else: #object
            return self.to_primitive('String').to_string() 
            
            
    def to_object(self):
        typ = self.Class
        if typ=='Null' or typ=='Undefined':
            raise TypeError('')
        elif typ=='Boolean': # Unsure here... todo repair here
            return self
        elif typ=='Number': #?
            return self
        elif typ=='String': #? 
            return self
        else: #object
            return self

    def to_int32(self):
        num = self.to_number()
        if num.is_nan() or num.is_infinity():
            return Js(0)
        val = num.value
        pos_int = int(val)
        int32 = pos_int % 0x10000
        num.value = int32 - 0x8000 if int32 > 0x8000 else int32
        return num

    def to_int(self):
        num = self.to_number()
        if num.is_nan():
            return Js(0)
        elif num.is_infinity():
            return num
        num.value = int(num)
        return num

    def to_unit32(self):
        num = self.to_number()
        if num.is_nan() or num.is_infinity():
            return Js(0)
        num.value = int(num.value) % 0x10000
        return num
    
    def same_as(self, other):
        typ = self.Class
        if typ!=other.Class:
            return False
        if typ=='Undefined' or typ=='Null':
            return True
        if typ=='Boolean' or typ=='Number' or typ=='String':
            return self.value==other.value
        else: #object
            return self is other #Id compare.

    #Not to be used by translation (only internal use)
    def __getitem__(self, item):
        return self.get(str(item))

    def __setitem__(self, key, value):
        self.put(str(key),  Js(value))

    def __len__(self):
        try:
            l = int(self.get('length').value)
            return l
        except:
            raise TypeError('This object (%s) does not have length property'%self.Class)
    #Oprators-------------
    #Unary, other will be implemented as functions. Increments and decrements 
    # will be methods of Number class
    def __neg__(self): #-u
        return Js(-self.to_number().value)
    
    def __pos__(self): #+u
        return self.to_number()
    
    def __inv__(self): #~u    this one may be wrong! check it when implementing other bitwise ops.
        return Js(~self.to_number().value)
    
    def neg(self): # !u  cant do 'not u' :(
        return Js(not self.to_boolean().value)
    
    def __nonzero__(self): 
        return self.to_boolean().value
        
    def typeof(self): 
        if self.is_callable():
            return Js('function')
        return Js(self.typ().lower())
        
    #Bitwise operators
    #  <<, >>,  &, ^, | . I have NEVER used them in python so they can wait.
    
    # << 
    def __lshift__(self, other):
        raise NotImplementedError()
    
    # >>
    def __rshift__(self, other):
        raise NotImplementedError()
     
    # & 
    def __and__(self, other):
        raise NotImplementedError()
    
    # ^
    def __xor__(self, other): 
        raise NotImplementedError()
    
    # |
    def __or__(self, other):
        raise NotImplementedError()
        
    # Additive operators
    # + and - are implemented here
        
    # +
    def __add__(self, other):
        a = self.to_primitive()
        b = other.to_primitive()
        if a.Class=='String' or b.Class=='String':
            return Js(a.to_string().value+b.to_string().value)
        a = a.to_number()
        b = b.to_number()
        return Js(a.value+b.value)
    
    # -
    def __sub__(self, other):
        return Js(self.to_number().value-other.to_number().value)
    
    #Multiplicative operators
    # *, / and % are implemented here
    
    # *
    def __mul__(self, other):
        return Js(self.to_number().value*other.to_number().value)
        
    # /
    def __div__(self, other):
        a = self.to_number().value
        b = other.to_number().value
        if b:
            return Js(a/b)
        if not a or a!=a:
            return NaN
        return Infinity if a>0 else -Infinity
    
    # %
    def __mod__(self, other):
        a = self.to_number().value
        b = other.to_number().value
        if abs(a)==float('inf') or not b:
            return NaN
        if abs(b)==float('inf'):
            return Js(a)
        pyres = Js(a%b) #different signs in python and javascript
                        #python has the same sign as b and js has the same 
                        #sign as a.
        if a<0 and pyres.value>0:
            pyres.value -= abs(b)
        elif a>0 and pyres.value<0:
            pyres.value += abs(b)
        return Js(pyres)
        
    #Comparisons (I dont implement === and !== here, these
    # will be implemented as external functions later)
    # <, <=, !=, ==, >=, > are implemented here.
    
    def abstract_relational_comparison(self, other, self_first=True):
        ''' self<other if self_first else other<self.
           Returns the result of the question: is self smaller than other?
           in case self_first is false it returns the answer of:
                                               is other smaller than self.
           result is PyJs type: bool or undefined'''
        px = self.to_primitive('Number')
        py = other.to_primitive('Number')
        if not self_first: #reverse order
            px, py = py, px
        if not (px.Class=='String' and py.Class=='String'):
            px, py = px.to_number(), py.to_number()
            if px.is_nan() or py.is_nan():
                return undefined
            return Js(px.value<py.value) # same cmp algorithm
        else:
            # I am pretty sure that python has the same
            # string cmp algorithm but I have to confirm it
            return Js(px.value<py.value) 
        
    #<
    def __lt__(self, other): 
        res = self.abstract_relational_comparison(other, True)
        if res.is_undefined():
            return false
        return res
    
    #<=
    def __le__(self, other): 
        res = self.abstract_relational_comparison(other, False)
        if res.is_undefined():
            return false
        return res.neg() 
    
    #>=
    def __ge__(self, other): 
        res = self.abstract_relational_comparison(other, True)
        if res.is_undefined():
            return false
        return res.neg() 
    
    #>
    def __gt__(self, other): 
        res = self.abstract_relational_comparison(other, False)
        if res.is_undefined():
            return false
        return res
        
    def abstract_equality_comparison(self, other):
        ''' returns the result of JS == compare.
           result is PyJs type: bool'''
        tx, ty = self.Class, other.Class
        if tx==ty:
            if tx=='Undefined' or tx=='Null':
                return true
            if tx=='Number' or tx=='String' or tx=='Boolean':
                return Js(self.value==other.value)
            return Js(self is other) # Object
        elif (tx=='Undefined' and ty=='Null') or (ty=='Undefined' and tx=='Null'):
            return true
        elif tx=='Number' and ty=='String':
            return self.abstract_equality_comparison(other.to_number())
        elif tx=='String' and ty=='Number':
            return self.to_number().abstract_equality_comparison(other)
        elif tx=='Boolean':
            return self.to_number().abstract_equality_comparison(other)
        elif ty=='Boolean':
            return self.abstract_equality_comparison(other.to_number())
        elif (tx=='String' or tx=='Number') and other.is_object():
            return self.abstract_equality_comparison(other.to_primitive())
        elif (ty=='String' or ty=='Number') and self.is_object():
            return self.to_primitive().abstract_equality_comparison(other)
        else:
           return false
                
    #==
    def __eq__(self, other): 
        return self.abstract_equality_comparison(other)
           
    #!=
    def __ne__(self, other): 
        return self.abstract_equality_comparison(other).neg()
    
    #Other methods (instanceof)
    
    def instanceof(self, other):
        '''checks if self is instance of other'''
        if not other.hasattr('has_instance'):
            return false
        return other.has_instance(self)
        
    #iteration
    def __iter__(self):
        #Returns a generator of all own enumerable properties
        return (Js(name) for name in self.own if self.own[name]['enumerable'])
    
    def contains(self, other):
        if not self.is_object():
            raise TypeError("Cannot use 'in' operator to search in non object")
        return Js(self.has_property(other.to_string().value))
        
    #Other Special methods
    def __call__(self, *args):
        '''Call a property prop as a function (this will be global object).
        
        NOTE: dont pass this and arguments here, these will be added
        automatically!'''
        if not self.is_callable():
            raise TypeError('%s is not a function'%self.typeof())
        return self.call(this, args) # global value of this 
    
    def __repr__(self):
        return self.to_string().value
    
    def callprop(self, prop, *args):
        '''Call a property prop as a method (this will be self).
        
        NOTE: dont pass this and arguments here, these will be added
        automatically!'''
        cand = self.get(prop)
        if not cand.is_callable():
            raise TypeError('%s is not a function'%cand.typeof())
        return cand.call(self, args)


#Define some more classes representing operators:

def PyJsStrictEq(a, b):
    '''a===b'''
    tx, ty = a.Class, b.Class
    if tx!=ty:
        return false
    if tx=='Undefined' or tx=='Null':
        return true
    if a.is_primitive(): #string bool and number case
        return Js(a.value==b.value)
    return Js(a is b) # object comparison
    
  
def PyJsStrictNeq(a, b):
    ''' a!==b'''
    return PyJsStrictEq(a, b).neg()
    
def PyJsBshift(a, b):
    """a>>>b"""
    return Js(0)  #NOT IMPLEMENTED YET

def PyJsAdd(a, b):
    """stupid function but simplifies parsing process A LOT"""
    return a+b

def PyJsSub(a, b):
    return a-b

def PyJsComma(a, b):
    return b

class PyJsException(Exception):
    def __str__(self):
        if self.mes.Class=='Error':
            return 'UNKNOWN' #todo idk what to do here
        else:
            return str(self.mes)

def JsToPyException(js):
    temp = PyJsException()
    temp.mes = js
    return temp

def PyExceptionToJs(py):
    return py.mes

#Scope class it will hold all the variables accessible to user
class Scope:
    registered = set()

    def __init__(self, scope, closure=None):
        """Doc"""
        self.scope = scope
        self.closure = closure

    def get(self, lval):
        cand = self.scope.get(lval)
        if cand is not None:
            return cand
        if self.closure is None:
            raise ReferenceError(lval + ' is not defined')
        return self.closure.get(lval)

    def register(self, lval):
        # registered keeps only global registered variables
        if not self.closure:
            self.registered.add(lval)
        if lval not in self.scope:
            self.scope[lval] = undefined

    def put(self, lval, val, op=None):
        cand = self.scope.get(lval)
        if (cand is not None) or (self.closure is None): #If not found set global
            if op: #Increment or other assign operation eg: *=
                val = getattr(cand, OP_METHODS[op])(val)
            self.scope[lval] = val
            return val
        return self.closure.put(lval, val, op)

    def delete(self, lval): # i have to improve it because registered cant be deleted ...
        if lval in self.registered: #we can only delete global not registered lvals and this one is registered
            return false
        # Note registered keeps only global registered variables
        now = self
        while now.closure is not None: # we cant delete any variables from closures because they are all registered
            if lval in now.scope:
                return false
            now = now.closure
        if lval not in now.scope:  # lval not present in global
            return true
        del now.scope[lval]
        return true







  
##############################################################################
#Define types
    
#Object
class PyJsObject(PyJs):
    Class = 'Object'
    def __init__(self, prop_descs={}, prototype=None, extensible=True):
        self.prototype = prototype
        self.extensible = extensible
        self.own = {}
        for prop, desc in prop_descs.iteritems():
            self.define_own_property(prop, desc)
    
    
ObjectPrototype = PyJsObject()


#Function
class PyJsFunction(PyJs):
    Class = 'Function'
    def __init__(self, func, prototype=None, extensible=True, source=None):
        func = fix_js_args(func)
        self.code = func
        self.source = source if source else '{ [python code] }'
        self.func_name = func.func_name if not func.func_nam.startswith('PyJsInlineTemp') else ''
        self.extensible = extensible
        self.prototype = prototype
        self.own = {}
        #set own property length to the number of arguments
        self.define_own_property('length', {'value': Js(func.func_code.co_argcount-2), 'writable': False,
                                            'enumerable': False, 'configurable': False})
        # set own prototype
        proto = Js({})
        # constructor points to this function
        proto.define_own_property('constructor',{'value': self, 'writable': True,
                                                 'enumerable': False, 'configurable': True})
        self.define_own_property('prototype', {'value': proto, 'writable': True,
                                                 'enumerable': False, 'configurable': False})

    def construct(self, *args):
        proto = self.get('prototype')
        if not proto.is_object(): # set to standard prototype
            proto = ObjectPrototype
        obj = PyJsObject(prototype=proto)
        cand = self.call(obj, *args)
        return cand if cand.is_object() else obj
    
    def call(self, this, args=()):
        '''Calls this function and returns a result 
        (converted to PyJs type so func can return python types)
        
        this must be a PyJs object and args must be a python tuple of PyJs objects.
        
        arguments object is passed automatically and will be equal to Js(args) 
        (tuple converted to arguments object).You dont need to worry about number 
        of arguments you provide if you supply less then missing ones will be set 
        to undefined (but not present in arguments object).
        And if you supply too much then excess will not be passed 
        (but they will be present in arguments object).
        '''
        if not hasattr(args, '__iter__'):  #get rid of it later
            args = (args,)
        args = tuple(Js(e) for e in args) # this wont be needed later

        arguments = PyJsArguments(args, self) # tuple will be converted to arguments object.
        arglen = self.code.func_code.co_argcount - 2 #function expects this number of args.
        if len(args)>arglen:
            args = args[0:arglen]
        elif len(args)<arglen:
            args += (undefined,)*(arglen-len(args))
        args += this, arguments  #append extra params to the arg list
        return Js(self.code(*args))
        
    def has_instance(self, other):
        # I am not sure here so instanceof may not work lol.
        if not other.is_object():
            return false
        proto = self.get('prototype')
        if not proto.is_object():
            raise TypeError('Function has non-object prototype in instanceof check')
        while True:
            other = other.prototype
            if not other:  # todo make sure that the condition is not None or null
                return false
            if other is proto:
                return true
            
        
        

def Empty():
    return Js(None)



#Number
class PyJsNumber(PyJs):  #Note i dont implement +0 and -0. Just 0.
    Class = 'Number'
    INF = float('inf')
    NAN = float('nan')
    def is_infinity(self):
        return abs(self.value)==self.INF
        
    def is_nan(self):
        return self.value!=self.value #nan!=nan evaluates to true 
        
    def PostInc(self):
        self.value+=1
        return Js(self.value-1)
    
    def PreInc(self):
        self.value+=1
        return Js(self.value) # returning new instance !
    
    def PostDec(self):
        self.value-=1
        return Js(self.value+1) 
    
    def PreDec(self):
        self.value-=1
        return Js(self.value)


NumberPrototype = PyJsObject({}, ObjectPrototype)
Infinity = PyJsNumber(float('inf'), NumberPrototype)
NaN = PyJsNumber(float('nan'), NumberPrototype)



#String
class PyJsString(PyJs):
    Class = 'String'

StringPrototype = PyJsObject({}, ObjectPrototype)


#Boolean
class PyJsBoolean(PyJs):
    Class = 'Boolean'

BooleanPrototype = PyJsObject({}, ObjectPrototype) 
true = PyJsBoolean(True, BooleanPrototype)
false = PyJsBoolean(False, BooleanPrototype)


#Undefined
class PyJsUndefined(PyJs):
    Class = 'Undefined'
    def __init__(self):
        pass

undefined = PyJsUndefined()

#Null
class PyJsNull(PyJs):
    Class = 'Null'
    def __init__(self):
        pass
null = PyJsNull()

class PyJsArray(PyJs):
    Class = 'Array'
    def __init__(self, arr=[], prototype=None):
        if arr and arr[-1] is None:
            del arr[-1]
        self.extensible = True
        self.prototype = prototype
        self.own = {}
        self.define_own_property('length', {'value': Js(len(arr)), 'writable': True,
                                            'enumerable': False, 'configurable': False})
        for i, e in enumerate(arr):
            self.define_own_property(str(i), {'value': Js(e), 'writable': True,
                                              'enumerable': True, 'configurable': True})

    def put(self, prop, val, op=None):
        super(PyJsArray, self).put(prop, val, op)

ArrayPrototype = PyJsArray([], ObjectPrototype)

class PyJsArguments(PyJs):
    Class = 'Arguments'
    def __init__(self, args, callee):
        self.own = {}
        self.extensible = True
        self.prototype = ObjectPrototype
        self.define_own_property('length', {'value': Js(len(args)), 'writable': True,
                                            'enumerable': False, 'configurable': False})
        self.define_own_property('callee', {'value': callee, 'writable': True,
                                            'enumerable': False, 'configurable': False})
        for i, e in enumerate(args):
            self.put(str(i), Js(e))


#We can define function proto after number proto because func uses number in its init
FunctionPrototype = PyJsFunction(Empty, ObjectPrototype)



##############################################################################
# Import and fill prototypes here.

#this works only for data properties
def fill_prototype(prototype, Class, attrs, constructor=False):
    for i in dir(Class):
        e = getattr(Class, i)
        if hasattr(e, '__func__'):
            temp = PyJsFunction(e.__func__, FunctionPrototype)
            attrs = {k:v for k,v in attrs.iteritems()}
            attrs['value'] = temp
            prototype.define_own_property(i, attrs)
        if constructor:
            attrs['value'] = constructor
            prototype.define_own_property('constructor', attrs)
            
default_attrs = {'writable':True, 'enumerable':False, 'configurable':True}


PyJs.undefined = undefined
PyJs.Js = staticmethod(Js)

from prototypes import jsfunction, jsobject, jsnumber, jsstring, jsboolean
#Object proto
fill_prototype(ObjectPrototype, jsobject.ObjectPrototype, default_attrs)
#Define __proto__ accessor (this cant be done by fill_prototype since)
def __proto__(): 
    return this.prototype if this.prototype is not None else null
getter = PyJsFunction(__proto__, FunctionPrototype)
def __proto__(): pass
setter =  PyJsFunction(__proto__, FunctionPrototype)     
ObjectPrototype.define_own_property('__proto__', {'set': setter,
                                                  'get': getter,
                                                  'enumerable': False,
                                                  'configurable':True})


#Function proto
fill_prototype(FunctionPrototype, jsfunction.FunctionPrototype, default_attrs)
#Number proto
fill_prototype(NumberPrototype, jsnumber.NumberPrototype, default_attrs)
#String proto
fill_prototype(StringPrototype, jsstring.StringPrototype, default_attrs)
#Boolean proto
fill_prototype(BooleanPrototype, jsboolean.BooleanPrototype, default_attrs)



#########################################################################

from translators import constants, nodevisitor

def sim_translate(code):
    code = code.replace('var ', '')
    c, d = constants.remove_constants(code)
    return constants.recover_constants(nodevisitor.exp_translator(c), d)

def interactor(x):
    import sys, traceback
    js_code = raw_input(x)
    try:
        py_code = sim_translate(js_code)
        print py_code
    except SyntaxError:
        sys.stderr.write(traceback.format_exc())
        return ''
    return py_code


def appengine_line(code, d, var):
    try:
        raw = nodevisitor.exp_translator(code)
        py_code = constants.recover_constants(raw, d)
    except SyntaxError:
        return traceback.format_exc()
    except:
        return traceback.format_exc()
    try:
        return (py_code, str(eval(py_code)))
    except:
        return (py_code, traceback.format_exc(), 1)

def appengine(code):
    var = Scope(copy(scope))
    var.scope['this'] = var
    try:
        c, d = constants.remove_constants(code)
        c = c.replace('var ', '')
    except SyntaxError:
        return traceback.format_exc()
    except:
        return 'Internal parse error \n(%s)'%traceback.format_exc()
    lines = c.split(';')
    trans_res = '\n'
    py_res = '\n'
    stop_py = False
    for i, line in enumerate(lines, 1):
        line = line.replace('\n','').strip()
        if not line:
            continue
        res = appengine_line(line, d, var)
        if isinstance(res, basestring):
            return 'Parse error in line %d:\n\n%s'%(i, res)
        if len(res)==3:
            py_res+= res[1]+'\n'
            stop_py = True
        elif not stop_py:
            py_res+=res[1]+'\n'
        trans_res += res[0] + '\n'
    return 'TRANSLATION RESULT:\n%s\n\nOUT:\n%s'%(trans_res, py_res)
        
        
        
builtins = ('true','false','null','undefined','Infinity',
            'NaN')

scope = dict(zip(builtins, [eval(e) for e in builtins]))

JS_BUILTINS = {k:v for k,v in scope.iteritems()}


print 'Started test'
 #test
if __name__=='__main__':
    print ObjectPrototype.get('toString').callprop('call')
    print FunctionPrototype.own
    a=  null-Js(49404)
    x = a.put('ser', Js('der'))
    print Js(0) or Js('p') and Js(4.0000000000050000001)
    FunctionPrototype.put('Chuj', Js(409))
    for e in FunctionPrototype:
        print 'Obk', e.get('__proto__').get('__proto__').get('__proto__'), e
    import code
    s = Js(4)
    b = Js(6)
    s2 = Js(4)
    o =  ObjectPrototype
    o.put('x', Js(100))
    var = Scope(scope)
    e = code.InteractiveConsole(globals())
    #e.raw_input = interactor
    e.interact()
