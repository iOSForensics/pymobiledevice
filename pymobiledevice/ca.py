#!/usr/bin/env python3

"""
How to create a CA certificate with Python.

WARNING: This sample only demonstrates how to use the objects and methods,
         not how to create a safe and correct certificate.

Copyright (c) 2004 Open Source Applications Foundation.
Authors: Heikki Toivonen
         Mathieu RENARD
"""
import base64

from M2Crypto import RSA, X509, EVP, m2, BIO
from M2Crypto.RSA import load_pub_key_bio
from pyasn1.type import univ
from pyasn1.codec.der import encoder as der_encoder
from pyasn1.codec.der import decoder as der_decoder


def convert_pkcs1_to_pkcs8_pubkey(bitsdata):
    pubkey_pkcs1_b64 = b''.join(bitsdata.split(b'\n')[1:-2])
    pubkey_pkcs1, restOfInput = der_decoder.decode(base64.b64decode(pubkey_pkcs1_b64))
    bitstring = univ.Sequence()
    bitstring.setComponentByPosition(0, univ.Integer(pubkey_pkcs1[0]))
    bitstring.setComponentByPosition(1, univ.Integer(pubkey_pkcs1[1]))
    bitstring = der_encoder.encode(bitstring)
    try:
        bitstring = ''.join([('00000000' + bin(ord(x))[2:])[-8:] for x in list(bitstring)])
    except:
        bitstring = ''.join([('00000000' + bin(x)[2:])[-8:] for x in list(bitstring)])
    bitstring = univ.BitString("'%s'B" % bitstring)
    pubkeyid = univ.Sequence()
    pubkeyid.setComponentByPosition(0, univ.ObjectIdentifier('1.2.840.113549.1.1.1'))  # == OID for rsaEncryption
    pubkeyid.setComponentByPosition(1, univ.Null(''))
    pubkey_seq = univ.Sequence()
    pubkey_seq.setComponentByPosition(0, pubkeyid)
    pubkey_seq.setComponentByPosition(1, bitstring)
    base64.MAXBINSIZE = (64 // 4) * 3
    res = b"-----BEGIN PUBLIC KEY-----\n"
    res += base64.b64encode(der_encoder.encode(pubkey_seq))
    res += b"\n-----END PUBLIC KEY-----"
    return res


def generate_rsa_key():
    return RSA.gen_key(2048, m2.RSA_F4)


def make_pkey(key):
    pkey = EVP.PKey()
    pkey.assign_rsa(key)
    return pkey


def make_request(pkey, cn):
    req = X509.Request()
    req.set_version(2)
    req.set_pubkey(pkey)
    name = X509.X509_Name()
    name.CN = cn
    req.set_subject_name(name)
    ext1 = X509.new_extension('subjectAltName', 'DNS:foobar.example.com')
    ext2 = X509.new_extension('nsComment', 'Hello there')
    extstack = X509.X509_Extension_Stack()
    extstack.push(ext1)
    extstack.push(ext2)

    assert (extstack[1].get_name() == 'nsComment')

    req.add_extensions(extstack)
    return req


def make_cert(req, caPkey):
    pkey = req.get_pubkey()
    # if not req.verify(woop.pkey):
    if not req.verify(pkey):
        # XXX What error object should I use?
        raise ValueError('Error verifying request')
    sub = req.get_subject()
    # If this were a real certificate request, you would display
    # all the relevant data from the request and ask a human operator
    # if you were sure. Now we just create the certificate blindly based
    # on the request.
    cert = X509.X509()
    # We know we are making CA cert now...
    # Serial defaults to 0.
    cert.set_serial_number(1)
    cert.set_version(2)
    cert.set_subject(sub)
    issuer = X509.X509_Name()
    issuer.CN = 'The Issuer Monkey'
    issuer.O = 'The Organization Otherwise Known as My CA, Inc.'
    cert.set_issuer(issuer)
    cert.set_pubkey(pkey)
    notBefore = m2.x509_get_not_before(cert.x509)
    notAfter = m2.x509_get_not_after(cert.x509)
    m2.x509_gmtime_adj(notBefore, 0)
    days = 30
    m2.x509_gmtime_adj(notAfter, 60 * 60 * 24 * days)
    cert.add_ext(
        X509.new_extension('subjectAltName', 'DNS:foobar.example.com'))
    ext = X509.new_extension('nsComment', 'M2Crypto generated certificate')
    ext.set_critical(0)  # Defaults to non-critical, but we can also set it
    cert.add_ext(ext)
    cert.sign(caPkey, 'sha1')

    assert (cert.get_ext('subjectAltName').get_name() == 'subjectAltName')
    assert (cert.get_ext_at(0).get_name() == 'subjectAltName')
    assert (cert.get_ext_at(0).get_value() == 'DNS:foobar.example.com')

    return cert


def ca():
    key = generate_rsa_key()
    pkey = make_pkey(key)
    req = make_request(pkey)
    cert = make_cert(req, pkey)
    return (cert, pkey)


def ca_do_everything(DevicePublicKey):
    rsa = generate_rsa_key()
    privateKey = make_pkey(rsa)
    req = make_request(privateKey, "The Issuer Monkey")
    cert = make_cert(req, privateKey)
    rsa2 = load_pub_key_bio(BIO.MemoryBuffer(
        convert_pkcs1_to_pkcs8_pubkey(DevicePublicKey)))
    pkey2 = EVP.PKey()
    pkey2.assign_rsa(rsa2)
    req = make_request(pkey2, "Device")
    cert2 = make_cert(req, privateKey)
    return cert.as_pem(), privateKey.as_pem(None), cert2.as_pem()


if __name__ == '__main__':
    rsa = generate_rsa_key()
    pkey = make_pkey(rsa)
    print(pkey.as_pem(None))
    req = make_request(pkey, "The Issuer Monkey")
    cert = make_cert(req, pkey)
    print(cert.as_text())
    cert.save_pem('my_ca_cert.pem')
    rsa.save_key('my_key.pem', None)
