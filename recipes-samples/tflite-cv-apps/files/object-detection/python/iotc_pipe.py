import os
import pickle

DEFAULT_PIPE_PATH = "/tmp/iotc.pipe"

class IOTCPipe:

    is_read = False

    def __init__(self, pipe_name=None):
        if pipe_name is None:
            self.pipe_name = DEFAULT_PIPE_PATH
        else:
            self.pipe_name = pipe_name

        if not os.path.exists(self.pipe_name):
            os.mkfifo(self.pipe_name)

        self.is_read = False

    def __del__(self):
        if self.is_read is True:
            os.remove(self.pipe_name)

    @classmethod
    def send_str(cls, str):
        cls.__init__(cls)
        with open(cls.pipe_name, 'w') as pipe:
            pipe.write(str)
            pipe.flush()

    @classmethod
    def read_str(cls):
        cls.__init__(cls)
        cls.is_read = True

        with open(cls.pipe_name, 'r') as pipe:
            data = pipe.readline()
            return data

        return None

    @classmethod
    def send_object(cls,obj):
        cls.__init__(cls)

        with open(cls.pipe_name, 'wb') as pipe:
            pickled_data = pickle.dumps(obj)
            pipe.write(pickled_data)
            pipe.flush()

    @classmethod
    def read_object(cls):
        cls.__init__(cls)
        cls.is_read = True

        with open(cls.pipe_name, 'rb') as pipe:
            pickled_data = pipe.read()
            data = pickle.loads(pickled_data)
            return data

        return None

    @classmethod
    def send_key_value(cls,key,value):
        out = {}
        out[key] = value
        cls.send_object(out)
    
    @classmethod
    def read_key_value(cls):
        return cls.read_object()

if __name__ == "__main__":
    raw_str = "tv 75%"
    split = raw_str.split(' ')
    key = split[0]
    value = float(split[1].replace('%', 'e-2'))
    print(key)
    print(value)

    IOTCPipe().send_key_value(key,value)