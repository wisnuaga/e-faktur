from typing import Dict, List


def compare(pdf_data: Dict, djp_data: Dict) -> Dict:
    deviations = []
    fields = [
        "npwpPenjual","namaPenjual","npwpPembeli","namaPembeli",
        "nomorFaktur","tanggalFaktur","jumlahDpp","jumlahPpn", "jumlahPpnBm"
    ]

    for f in fields:
        pv = pdf_data.get(f)
        dv = djp_data.get(f)
        if pv != dv:
            deviations.append({
                "field": f,
                "pdf_value": pv,
                "djp_api_value": dv,
                "deviation_type": (
                    "missing_in_pdf" if pv in (None, "") and dv not in (None, "") else
                    "missing_in_api" if dv in (None, "") and pv not in (None, "") else
                    "mismatch"
                )
            })

    status = "validated_successfully" if not deviations else "validated_with_deviations"
    return {
        "status": status,
        "message": "Validation complete" if status=="validated_successfully" else f"Found {len(deviations)} deviation(s)",
        "validation_results": {
            "deviations": deviations,
            "validated_data": djp_data
        }
    }
