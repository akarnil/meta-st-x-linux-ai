from multiprocessing.connection import Listener
from multiprocessing.connection import Client

import pickle

class IOTC_IPC:
    PORT=6000
    ADDRESS="localhost"

    class Sender:
        con = None
        accepted = None

        def __init__(self):
            self.con = Listener((IOTC_IPC.ADDRESS, IOTC_IPC.PORT))
            self.accepted = self.con.accept()

        def __del__(self):
            if self.accepted is not None:
                self.accepted.close()
                self.con.close()

        def send_object(self,obj):
            if self.accepted is None:
                self.__init__(self)

            self.accepted.send(pickle.dumps(obj))

        def send_key_value(self,key,value):
            out = {}
            out[key] = value
            self.send_object(out)

    class Receiver:
        con = None
        running = True

        def __init__(self):
            while 1:
                try:
                    self.con = Client((IOTC_IPC.ADDRESS, IOTC_IPC.PORT))
                    break
                except:
                    pass

        def __del__(self):
            if self.con is not None:
                self.con.close()

        def read_object(self):
            if self.con is None:
                self.__init__(self)

            data = None
            data = self.con.recv()
            data = pickle.loads(data)

            return data


if __name__ == "__main__":
    # r = IOTC_IPC.Receiver
    x = IOTC_IPC.Sender()
    while 1:
        x.send_key_value("a", "b")