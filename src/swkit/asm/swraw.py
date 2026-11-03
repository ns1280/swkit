# -*- coding: utf-8 -*-
"""Minimal raw-IDispatch helper for SOLIDWORKS, usable from 64-bit CPython.

cscript/VBScript cannot hand SOLIDWORKS a proper double SAFEARRAY and comtypes
cannot convert VT_ARRAY|VT_DISPATCH return values, so the few calls that need
arrays are issued here through IDispatch::Invoke with hand-built VARIANTs.
"""
import ctypes
from ctypes import POINTER, byref, c_byte, c_double, c_long, c_uint, c_ulong, c_ushort, c_void_p, c_wchar_p

oleaut32 = ctypes.WinDLL("oleaut32")

VT_I4 = 3
VT_R8 = 5
VT_BSTR = 8
VT_DISPATCH = 9
VT_BOOL = 11
VT_VARIANT = 12
VT_UNKNOWN = 13
VT_ARRAY = 0x2000

DISPATCH_METHOD = 1
DISPATCH_PROPERTYGET = 2
DISPATCH_PROPERTYPUT = 4
DISPID_PROPERTYPUT = -3


class GUID(ctypes.Structure):
    _fields_ = [("Data1", c_ulong), ("Data2", c_ushort), ("Data3", c_ushort), ("Data4", c_byte * 8)]


class VARIANT(ctypes.Structure):
    _fields_ = [("vt", c_ushort), ("r1", c_ushort), ("r2", c_ushort), ("r3", c_ushort), ("v", c_byte * 16)]


class DISPPARAMS(ctypes.Structure):
    _fields_ = [("rgvarg", POINTER(VARIANT)), ("rgdispidNamedArgs", POINTER(c_long)),
                ("cArgs", c_uint), ("cNamedArgs", c_uint)]


class EXCEPINFO(ctypes.Structure):
    _fields_ = [("wCode", c_ushort), ("wReserved", c_ushort), ("bstrSource", c_void_p),
                ("bstrDescription", c_void_p), ("bstrHelpFile", c_void_p), ("dwHelpContext", c_ulong),
                ("pvReserved", c_void_p), ("pfnDeferredFillIn", c_void_p), ("scode", c_long)]


class SAFEARRAYBOUND(ctypes.Structure):
    _fields_ = [("cElements", c_ulong), ("lLbound", c_long)]


class SAFEARRAY(ctypes.Structure):
    _fields_ = [("cDims", c_ushort), ("fFeatures", c_ushort), ("cbElements", c_ulong),
                ("cLocks", c_ulong), ("pvData", c_void_p), ("rgsabound", SAFEARRAYBOUND * 1)]


_GetIDsOfNames = ctypes.WINFUNCTYPE(c_long, c_void_p, POINTER(GUID), POINTER(c_wchar_p), c_uint, c_uint, POINTER(c_long))
_Invoke = ctypes.WINFUNCTYPE(c_long, c_void_p, c_long, POINTER(GUID), c_uint, c_ushort,
                             POINTER(DISPPARAMS), POINTER(VARIANT), POINTER(EXCEPINFO), POINTER(c_uint))

oleaut32.SysAllocString.restype = ctypes.c_uint64
oleaut32.SysAllocString.argtypes = [c_wchar_p]
oleaut32.SafeArrayCreate.restype = ctypes.c_uint64
oleaut32.SafeArrayCreate.argtypes = [c_ushort, c_uint, POINTER(SAFEARRAYBOUND)]
oleaut32.SafeArrayAccessData.argtypes = [c_void_p, POINTER(c_void_p)]
oleaut32.SafeArrayUnaccessData.argtypes = [c_void_p]
oleaut32.SafeArrayDestroy.argtypes = [c_void_p]

NULL_IID = GUID()


def ptr_of(obj):
    """Raw interface pointer (as int) of a comtypes object."""
    return ctypes.cast(obj, c_void_p).value


def _vtbl_fn(pdisp, index, proto):
    vtbl = ctypes.cast(ctypes.cast(pdisp, POINTER(c_void_p))[0], POINTER(c_void_p))
    return proto(vtbl[index])


def _as_ptr(pdisp):
    if isinstance(pdisp, int):
        return c_void_p(pdisp)
    return c_void_p(pdisp.value)


def dispid(pdisp, name):
    fn = _vtbl_fn(pdisp, 5, _GetIDsOfNames)
    d = c_long()
    hr = fn(_as_ptr(pdisp), byref(NULL_IID), (c_wchar_p * 1)(name), 1, 0, byref(d))
    if hr != 0:
        raise OSError("GetIDsOfNames(%s) hr=0x%08x" % (name, hr & 0xFFFFFFFF))
    return d.value


def _make_var(value):
    v = VARIANT()
    if isinstance(value, bool):
        v.vt = VT_BOOL
        ctypes.memmove(v.v, byref(ctypes.c_short(-1 if value else 0)), 2)
    elif isinstance(value, int):
        v.vt = VT_I4
        ctypes.memmove(v.v, byref(c_long(value)), 4)
    elif isinstance(value, float):
        v.vt = VT_R8
        ctypes.memmove(v.v, byref(c_double(value)), 8)
    elif isinstance(value, str):
        v.vt = VT_BSTR
        ctypes.memmove(v.v, byref(c_void_p(oleaut32.SysAllocString(value))), 8)
    elif isinstance(value, RawPtr):
        v.vt = value.vt
        ctypes.memmove(v.v, byref(c_void_p(value.ptr)), 8)
    elif value is None:
        v.vt = VT_DISPATCH
        ctypes.memmove(v.v, byref(c_void_p(None)), 8)
    elif isinstance(value, VARIANT):
        v = value
    else:  # raw pointer / dispatch
        v.vt = VT_DISPATCH
        ctypes.memmove(v.v, byref(c_void_p(value)), 8)
    return v


def make_r8_array(values):
    bound = SAFEARRAYBOUND(len(values), 0)
    psa = oleaut32.SafeArrayCreate(VT_R8, 1, byref(bound))
    pv = c_void_p()
    oleaut32.SafeArrayAccessData(psa, byref(pv))
    arr = (c_double * len(values))(*values)
    ctypes.memmove(pv, arr, 8 * len(values))
    oleaut32.SafeArrayUnaccessData(psa)
    v = VARIANT()
    v.vt = VT_R8 | VT_ARRAY
    ctypes.memmove(v.v, byref(c_void_p(psa)), 8)
    return v


def make_dispatch_array(ptrs, as_variant=False, elem_vt=VT_DISPATCH):
    """把一组接口指针打包成 SAFEARRAY。

    as_variant=False → VT_ARRAY|VT_DISPATCH（元素为 IDispatch*）
    as_variant=True  → VT_ARRAY|VT_VARIANT（每个元素是 VT_DISPATCH 的 VARIANT）
    SolidWorks 的 MateData.EntitiesToMate 在不同版本接受其中一种。
    """
    n = len(ptrs)
    bound = SAFEARRAYBOUND(n, 0)
    if as_variant:
        psa = oleaut32.SafeArrayCreate(VT_VARIANT, 1, byref(bound))
        pv = c_void_p()
        oleaut32.SafeArrayAccessData(psa, byref(pv))
        arr = (VARIANT * n)()
        for i, p in enumerate(ptrs):
            arr[i].vt = elem_vt
            ctypes.memmove(arr[i].v, byref(c_void_p(p)), 8)
        ctypes.memmove(pv, arr, ctypes.sizeof(VARIANT) * n)
        oleaut32.SafeArrayUnaccessData(psa)
        v = VARIANT()
        v.vt = VT_VARIANT | VT_ARRAY
    else:
        psa = oleaut32.SafeArrayCreate(VT_DISPATCH, 1, byref(bound))
        pv = c_void_p()
        oleaut32.SafeArrayAccessData(psa, byref(pv))
        arr = (c_void_p * n)(*ptrs)
        ctypes.memmove(pv, arr, ctypes.sizeof(c_void_p) * n)
        oleaut32.SafeArrayUnaccessData(psa)
        v = VARIANT()
        v.vt = VT_DISPATCH | VT_ARRAY
    ctypes.memmove(v.v, byref(c_void_p(psa)), 8)
    return v


def call(pdisp, name, args=(), put=False, prop=False):
    """Invoke a method / property on a raw IDispatch pointer; returns a VARIANT."""
    pdisp = _as_ptr(pdisp).value
    d = dispid(pdisp, name)
    n = len(args)
    holder = (VARIANT * max(n, 1))()
    for i, a in enumerate(args):
        holder[n - 1 - i] = _make_var(a)
    dp = DISPPARAMS()
    dp.rgvarg = ctypes.cast(holder, POINTER(VARIANT))
    dp.cArgs = n
    if put:
        dp.rgdispidNamedArgs = ctypes.cast(ctypes.pointer(c_long(DISPID_PROPERTYPUT)), POINTER(c_long))
        dp.cNamedArgs = 1
    res = VARIANT()
    ei = EXCEPINFO()
    ae = c_uint()
    flags = DISPATCH_PROPERTYPUT if put else (DISPATCH_PROPERTYGET if prop else DISPATCH_METHOD)
    fn = _vtbl_fn(pdisp, 6, _Invoke)
    hr = fn(_as_ptr(pdisp), d, byref(NULL_IID), 0, flags, byref(dp), byref(res), byref(ei), byref(ae))
    if hr != 0:
        raise OSError("%s hr=0x%08x arg=%d" % (name, hr & 0xFFFFFFFF, ae.value))
    return res


class RawPtr(object):
    """Wrap a raw interface pointer together with the VARIANT type to use."""

    def __init__(self, ptr, vt=VT_DISPATCH):
        self.ptr = ptr
        self.vt = vt


def var_ptr(v):
    return ctypes.cast(v.v, POINTER(c_void_p))[0]


def var_double(v):
    return ctypes.cast(v.v, POINTER(c_double))[0]


def var_bstr(v):
    p = ctypes.cast(v.v, POINTER(c_void_p))[0]
    return ctypes.wstring_at(p) if p else ""


def array_items(v):
    """Return the elements of a SAFEARRAY held in a VARIANT as a Python list."""
    if not (v.vt & VT_ARRAY):
        raise ValueError("not an array variant (vt=%d)" % v.vt)
    psa = ctypes.cast(v.v, POINTER(c_void_p))[0]
    sa = ctypes.cast(psa, POINTER(SAFEARRAY)).contents
    n = sa.rgsabound[0].cElements
    base = v.vt & ~VT_ARRAY
    pv = c_void_p()
    oleaut32.SafeArrayAccessData(psa, byref(pv))
    out = []
    for i in range(n):
        addr = pv.value + i * 8
        if base == VT_R8:
            out.append(ctypes.cast(addr, POINTER(c_double))[0])
        else:
            out.append(ctypes.cast(addr, POINTER(c_void_p))[0])
    oleaut32.SafeArrayUnaccessData(psa)
    return out
