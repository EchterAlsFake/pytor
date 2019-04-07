import os
import re
from abc import ABC
from abc import abstractmethod
from base64 import b32encode
from hashlib import sha1
from typing import BinaryIO

from Crypto.PublicKey import RSA


__all__ = [
    'OnionV2',
    'OnionV3',
]


class EmptyDirException(Exception):
    pass


class Onion(ABC):
    '''
    Interface to implement hidden services keys managment
    '''

    _priv = None
    _pub = None
    _hidden_service_path = None
    _version = None

    def __init__(self,
                 private_key: bytes = None,
                 hidden_service_path: str = None):

        if hidden_service_path:
            try:
                self.load_hidden_service(hidden_service_path)
            except EmptyDirException:
                pass
            self._hidden_service_path = hidden_service_path
        if private_key:
            self.set_private_key(private_key)
        if not self._priv:
            self.gen_new_private_key()

    @abstractmethod
    def gen_new_private_key(self) -> None:
        'Generate new private key'
        ...

    @abstractmethod
    def set_private_key_from_file(self, file: BinaryIO):
        'Load private key from file'
        ...

    @abstractmethod
    def set_private_key(self, key: bytes) -> None:
        'Add private key'
        ...

    @abstractmethod
    def _save_keypair(self, key) -> None:
        'Generate pub key from priv key and save both in instance'
        ...

    @abstractmethod
    def load_hidden_service(self, path: str) -> None:
        'Load key from hidden service'
        ...

    @abstractmethod
    def write_hidden_service(self, path: str, force: bool = False) -> None:
        'Write hidden service keys to directory'
        ...

    def get_available_private_key_formats(self) -> list:
        'Get private key export availables formats'
        r = re.compile(r'_get_private_key_has_([a-z]+)')
        formats = []
        for method in dir(self):
            m = r.match(method)
            if m:
                formats.append(m[1])
        return formats

    def get_private_key(self, format: str = 'native'):
        'Get the private key as specified format'
        method = '_get_private_key_has_{format}'.format(
            format=format
        )
        if not hasattr(self, method) and not callable(getattr(self, method)):
            raise NotImplementedError('Method {method} if not implemented')
        return getattr(self, method)()

    @abstractmethod
    def _get_private_key_has_native(self) -> bytes:
        'Get private key like in tor native format'
        ...

    @abstractmethod
    def get_public_key(self) -> bytes:
        'Compute public key'
        if not self._priv:
            raise Exception('No private key has been set')

    @abstractmethod
    def get_onion_str(self) -> str:
        'Compute onion address string'
        ...

    @property
    def onion_address(self) -> str:
        return "{onion}.onion".format(
            onion=self.get_onion_str()
        )

    @property
    def version(self) -> str:
        return str(self._version)


class OnionV2(Onion):
    '''
    Tor onion address v2 implement
    '''

    _version = 2

    def gen_new_private_key(self) -> None:
        'Generate new 1024 bits RSA key for hidden service'
        self._save_keypair(RSA.generate(bits=1024))

    def _save_keypair(self, key: RSA.RsaKey) -> None:
        self._priv = key.exportKey("PEM")
        self._pub = key.publickey().exportKey("DER")

    def set_private_key(self, key: bytes) -> None:
        'Add private key'
        self._save_keypair(RSA.importKey(key.strip()))

    def set_private_key_from_file(self, file: BinaryIO):
        'Load private key from file'
        self.set_private_key(file.read())

    def _get_private_key_has_native(self) -> bytes:
        'Get RSA private key like in PEM'
        return self._get_private_key_has_pem()

    def _get_private_key_has_pem(self) -> bytes:
        'Get RSA private key like in PEM'
        return RSA.importKey(self._priv).exportKey("PEM")

    def get_public_key(self) -> bytes:
        'Compute public key'
        super().get_public_key()
        return self._pub

    def load_hidden_service(self, path: str) -> None:
        if not os.path.isdir(path):
            raise Exception(
                '{path} should be an existing directory'.format(path=path)
            )
        if 'private_key' not in os.listdir(path):
            raise EmptyDirException(
                'private_key file not found in {path}'.format(path=path)
            )
        with open(os.path.join(path, 'private_key'), 'rb') as f:
            self.set_private_key_from_file(f)

    def write_hidden_service(self, path: str = None,
                             force: bool = False) -> None:
        path = path or self._hidden_service_path
        if not path:
            raise Exception('Missing hidden service path')
        if not os.path.exists(path):
            raise Exception(
                '{path} should be an existing directory'.format(path=path)
            )
        if os.path.exists(os.path.join(path, 'private_key')) and not force:
            raise Exception(
                'Use force=True for non empty hidden service directory'
            )
        with open(os.path.join(path, 'private_key'), 'wb') as f:
            f.write(self._get_private_key_has_native())
        with open(os.path.join(path, 'hostname'), 'w') as f:
            f.write(self.onion_address)

    def get_onion_str(self) -> str:
        'Compute onion address string'
        return b32encode(sha1(self._pub[22:]).digest()[:10]).decode().lower()


class OnionV3(Onion):
    '''
    Tor onion address v3 implement
    '''

    _version = 3