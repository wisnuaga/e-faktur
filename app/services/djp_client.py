from typing import Dict
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from app.core.normalizers import normalize_company


def fetch_djp_xml(url: str) -> Dict[str, str]:
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    return {
        "npwpPenjual": root.findtext("npwpPenjual"),
        "namaPenjual": normalize_company(root.findtext("namaPenjual")),
        "npwpPembeli": root.findtext("npwpLawanTransaksi"),
        "namaPembeli": normalize_company(root.findtext("namaLawanTransaksi")),
        "nomorFaktur": root.findtext("nomorFaktur"),
        "tanggalFaktur": datetime.strptime(root.findtext("tanggalFaktur"), "%d/%m/%Y").date(),
        "jumlahDpp": float(root.findtext("jumlahDpp")),
        "jumlahPpn": float(root.findtext("jumlahPpn")),
    }


def parse_xml_response(xml_str: str) -> Dict[str, str]:
    """Parse XML string response from DJP API."""
    root = ET.fromstring(xml_str)
    return {
        "npwpPenjual": root.findtext("npwpPenjual"),
        "namaPenjual": normalize_company(root.findtext("namaPenjual")),
        "npwpPembeli": root.findtext("npwpLawanTransaksi"),
        "namaPembeli": normalize_company(root.findtext("namaLawanTransaksi")),
        "nomorFaktur": root.findtext("nomorFaktur"),
        "tanggalFaktur": datetime.strptime(root.findtext("tanggalFaktur"), "%d/%m/%Y").date(),
        "jumlahDpp": float(root.findtext("jumlahDpp")),
        "jumlahPpn": float(root.findtext("jumlahPpn")),
    }
