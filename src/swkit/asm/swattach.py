# -*- coding: utf-8 -*-
"""Attach to the running SldWorks via CoCreateInstance (LOCAL_SERVER)."""
import ctypes
import comtypes
from comtypes import GUID, IUnknown
from comtypes.automation import IDispatch
from comtypes.client.dynamic import Dispatch

CLSID_SLDWORKS = GUID("{6af263bb-eb9f-4176-89e9-4f892eb0ca3d}")


def attach():
    p = ctypes.POINTER(IDispatch)()
    ctypes.oledll.ole32.CoCreateInstance(
        ctypes.byref(CLSID_SLDWORKS), None, 4,  # CLSCTX_LOCAL_SERVER
        ctypes.byref(IDispatch._iid_), ctypes.byref(p))
    return Dispatch(p)
