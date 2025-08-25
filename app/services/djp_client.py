from typing import Dict
import requests
import xml.etree.ElementTree as ET


def fetch_djp_xml(url: str) -> Dict[str, str]:
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    return {
        "npwpPenjual": root.findtext("npwpPenjual"),
        "namaPenjual": root.findtext("namaPenjual"),
        "npwpPembeli": root.findtext("npwpLawanTransaksi"),
        "namaPembeli": root.findtext("namaLawanTransaksi"),
        "nomorFaktur": root.findtext("nomorFaktur"),
        "tanggalFaktur": root.findtext("tanggalFaktur"),
        "jumlahDpp": root.findtext("jumlahDpp"),
        "jumlahPpn": root.findtext("jumlahPpn"),
    }


def parse_xml_response(xml_str: str) -> Dict[str, str]:
    """Parse XML string response from DJP API."""
    root = ET.fromstring(xml_str)
    return {
        "npwpPenjual": root.findtext("npwpPenjual"),
        "namaPenjual": root.findtext("namaPenjual"),
        "npwpPembeli": root.findtext("npwpLawanTransaksi"),
        "namaPembeli": root.findtext("namaLawanTransaksi"),
        "nomorFaktur": root.findtext("nomorFaktur"),
        "tanggalFaktur": root.findtext("tanggalFaktur"),
        "jumlahDpp": root.findtext("jumlahDpp"),
        "jumlahPpn": root.findtext("jumlahPpn"),
    }
