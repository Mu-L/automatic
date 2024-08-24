import os
import sys
import ctypes
import shutil
import zipfile
import urllib.request
from modules import rocm


DLL_MAPPING = {
    'cublas.dll': 'cublas64_11.dll',
    'cusparse.dll': 'cusparse64_11.dll',
    'nvrtc.dll': 'nvrtc64_112_0.dll',
}
HIPSDK_TARGETS = ['rocblas.dll', 'rocsolver.dll', f'hiprtc{"".join([v.zfill(2) for v in rocm.version.split(".")])}.dll']
ZLUDA_TARGETS = ('nvcuda.dll', 'nvml.dll',)


def get_path() -> str:
    return os.path.abspath(os.environ.get('ZLUDA', '.zluda'))


def install(zluda_path: os.PathLike) -> None:
    if os.path.exists(zluda_path):
        return

    default_hash = None
    if rocm.version == "6.1":
        default_hash = '2f2e38a8adebb456ad75390e60871f2c8ba18fa7'
    elif rocm.version == "5.7":
        default_hash = '11cc5844514f93161e0e74387f04e2c537705a82'
    else:
        raise RuntimeError(f'Unsupported HIP SDK version: {rocm.version}')
    urllib.request.urlretrieve(f'https://github.com/lshqqytiger/ZLUDA/releases/download/rel.{os.environ.get("ZLUDA_HASH", default_hash)}/ZLUDA-windows-amd64.zip', '_zluda')
    with zipfile.ZipFile('_zluda', 'r') as archive:
        infos = archive.infolist()
        for info in infos:
            if not info.is_dir():
                info.filename = os.path.basename(info.filename)
                archive.extract(info, '.zluda')
    os.remove('_zluda')


def uninstall() -> None:
    if os.path.exists('.zluda'):
        shutil.rmtree('.zluda')


def make_copy(zluda_path: os.PathLike) -> None:
    for k, v in DLL_MAPPING.items():
        if not os.path.exists(os.path.join(zluda_path, v)):
            try:
                os.link(os.path.join(zluda_path, k), os.path.join(zluda_path, v))
            except Exception:
                shutil.copyfile(os.path.join(zluda_path, k), os.path.join(zluda_path, v))


def load(zluda_path: os.PathLike) -> None:
    for v in HIPSDK_TARGETS:
        ctypes.windll.LoadLibrary(os.path.join(rocm.path, 'bin', v))
    for v in ZLUDA_TARGETS:
        ctypes.windll.LoadLibrary(os.path.join(zluda_path, v))
    for v in DLL_MAPPING.values():
        ctypes.windll.LoadLibrary(os.path.join(zluda_path, v))

    def conceal():
        import torch # pylint: disable=unused-import
        platform = sys.platform
        sys.platform = ""
        from torch.utils import cpp_extension
        sys.platform = platform
        cpp_extension.IS_WINDOWS = platform == "win32"
        cpp_extension.IS_MACOS = False
        cpp_extension.IS_LINUX = platform.startswith('linux')
        def _join_rocm_home(*paths) -> str:
            return os.path.join(cpp_extension.ROCM_HOME, *paths)
        cpp_extension._join_rocm_home = _join_rocm_home # pylint: disable=protected-access
    rocm.conceal = conceal
