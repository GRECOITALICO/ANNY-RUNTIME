import ctypes
from ctypes import util

x11 = ctypes.cdll.LoadLibrary(util.find_library('X11'))
print(x11)
