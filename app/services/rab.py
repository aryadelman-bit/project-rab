from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import datetime
from typing import Any
from uuid import uuid4

from app.config import resolve_sbm_source
from app.schemas import (
    ActivityPayload,
    BudgetLinePayload,
    BudgetLineUpdatePayload,
    FormSelectionPayload,
    ManualAccountPayload,
    SubComponentPayload,
)
from app.services.sbm import import_sbm_workbook, normalize_key, seed_fallback_costs

LOCATION_TEXT_ALIASES = {
    "DKIJAKARTA": "DKI JAKARTA",
    "SUMATRAUTARA": "SUMATRA UTARA",
    "SUMATERAUTARA": "SUMATRA UTARA",
    "SUMATRABARAT": "SUMATRA BARAT",
    "SUMATRATENGAH": "SUMATRA TENGAH",
    "SUMATRASELATAN": "SUMATRA SELATAN",
    "KEPULAUANRIAU": "KEPULAUAN RIAU",
    "BANGKABELITUNG": "BANGKA BELITUNG",
    "DI YOGYAKARTA": "D.I. YOGYAKARTA",
    "DIYOGYAKARTA": "D.I. YOGYAKARTA",
    "JAWABARAT": "JAWA BARAT",
    "JAWATENGAH": "JAWA TENGAH",
    "JAWATIMUR": "JAWA TIMUR",
    "KALIMANTANBARAT": "KALIMANTAN BARAT",
    "KALIMANTANTENGAH": "KALIMANTAN TENGAH",
    "KALIMANTANSELATAN": "KALIMANTAN SELATAN",
    "KALIMANTANTIMUR": "KALIMANTAN TIMUR",
    "KALIMANTANUTARA": "KALIMANTAN UTARA",
    "SULAWESIUTARA": "SULAWESI UTARA",
    "SULAWESITENGAH": "SULAWESI TENGAH",
    "SULAWESISELATAN": "SULAWESI SELATAN",
    "SULAWESITENGGARA": "SULAWESI TENGGARA",
    "SULAWESIBARAT": "SULAWESI BARAT",
    "NUSATENGGARABARAT": "NUSA TENGGARA BARAT",
    "NUSATENGGARATIMUR": "NUSA TENGGARA TIMUR",
    "MALUKUUTARA": "MALUKU UTARA",
    "PAPUABARAT": "PAPUA BARAT",
    "PAPUABARATDAYA": "PAPUA BARAT DAYA",
    "PAPUASELATAN": "PAPUA SELATAN",
    "PAPUATENGAH": "PAPUA TENGAH",
    "PAPUAPEGUNUNGAN": "PAPUA PEGUNUNGAN",
}

CITY_PROVINCE_OVERRIDES = {
    normalize_key("AMBON"): "MALUKU",
    normalize_key("BALIKPAPAN"): "KALIMANTAN TIMUR",
    normalize_key("BANDA ACEH"): "ACEH",
    normalize_key("BANDAR LAMPUNG"): "LAMPUNG",
    normalize_key("BANDUNG"): "JAWA BARAT",
    normalize_key("BANJARMASIN"): "KALIMANTAN SELATAN",
    normalize_key("BATAM"): "KEPULAUAN RIAU",
    normalize_key("BENGKULU"): "BENGKULU",
    normalize_key("BIAK"): "PAPUA",
    normalize_key("DENPASAR"): "BALI",
    normalize_key("GORONTALO"): "GORONTALO",
    normalize_key("JAKARTA"): "DKI JAKARTA",
    normalize_key("JAMBI"): "JAMBI",
    normalize_key("JAYAPURA"): "PAPUA",
    normalize_key("KENDARI"): "SULAWESI TENGGARA",
    normalize_key("KUPANG"): "NUSA TENGGARA TIMUR",
    normalize_key("MAKASSAR"): "SULAWESI SELATAN",
    normalize_key("MALANG"): "JAWA TIMUR",
    normalize_key("MAMUJU"): "SULAWESI BARAT",
    normalize_key("MANADO"): "SULAWESI UTARA",
    normalize_key("MANOKWARI"): "PAPUA BARAT",
    normalize_key("MATARAM"): "NUSA TENGGARA BARAT",
    normalize_key("MEDAN"): "SUMATRA UTARA",
    normalize_key("PADANG"): "SUMATRA BARAT",
    normalize_key("PALANGKARAYA"): "KALIMANTAN TENGAH",
    normalize_key("PALEMBANG"): "SUMATRA SELATAN",
    normalize_key("PALU"): "SULAWESI TENGAH",
    normalize_key("PANGKAL PINANG"): "BANGKA BELITUNG",
    normalize_key("PEKANBARU"): "RIAU",
    normalize_key("PONTIANAK"): "KALIMANTAN BARAT",
    normalize_key("POSO"): "SULAWESI TENGAH",
    normalize_key("SEMARANG"): "JAWA TENGAH",
    normalize_key("SOLO"): "JAWA TENGAH",
    normalize_key("SORONG"): "PAPUA BARAT DAYA",
    normalize_key("SURABAYA"): "JAWA TIMUR",
    normalize_key("TANJUNG PANDAN"): "BANGKA BELITUNG",
    normalize_key("TANJUNG SELOR"): "KALIMANTAN UTARA",
    normalize_key("TERNATE"): "MALUKU UTARA",
    normalize_key("TIMIKA"): "PAPUA TENGAH",
    normalize_key("TOLI-TOLI"): "SULAWESI TENGAH",
    normalize_key("YOGYAKARTA"): "D.I. YOGYAKARTA",
}

PROVINCE_REFERENCE_CATEGORIES = (
    "consumption_regular",
    "daily_allowance_domestic",
    "hotel_domestic",
    "land_transport_domestic",
    "vehicle_rent",
    "airport_taxi_domestic",
)


def _json_loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "ya", "yes", "on"}


def _to_float(value: Any, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _excel_style_code(index: int) -> str:
    letters: list[str] = []
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        letters.append(chr(65 + remainder))
    return "".join(reversed(letters))


def _sorted_unique_strings(values: list[Any]) -> list[str]:
    seen: dict[str, str] = {}
    for value in values:
        if value in (None, ""):
            continue
        text = _clean_location_text(value)
        if not text:
            continue
        key = normalize_key(text)
        if not key or key in seen:
            continue
        seen[key] = text
    return sorted(seen.values(), key=lambda item: normalize_key(item))


def _clean_location_text(value: Any) -> str:
    text = " ".join(str(value).strip().split())
    return LOCATION_TEXT_ALIASES.get(normalize_key(text), text)


def _is_valid_location_value(value: Any, kind: str) -> bool:
    text = _clean_location_text(value)
    key = normalize_key(text)
    if not key:
        return False

    invalid_exact = {
        "NO",
        "NO.",
        "URAIAN",
        "PROVINSI",
        "KOTA",
        "ASAL",
        "TUJUAN",
        "SATUAN",
        "IBUKOTAPROVINSI",
        "KABUPATENKOTATUJUAN",
    }
    if key in invalid_exact:
        return False

    if kind == "province":
        invalid_keywords = ["PEJABAT", "FULLBOARD", "HALFDAY", "RAPAT"]
        return not any(keyword in key for keyword in invalid_keywords)

    return True


def _activity_form_catalog() -> list[dict[str, Any]]:
    return [
        {
            "code": "OFFICE_MEETING",
            "name": "Rapat di kantor dengan unit kerja lain / asosiasi / pelaku usaha",
            "description": "Rekomendasikan konsumsi rapat, ATK, suplai komputer, dan honor narasumber bila diperlukan.",
            "category": "koordinasi",
            "parameter_schema_json": json.dumps(
                [
                    {"name": "province", "label": "Provinsi lokasi", "type": "select", "reference_key": "provinces", "default": "DKI JAKARTA"},
                    {"name": "participant_count", "label": "Jumlah peserta", "type": "number", "default": 20},
                    {"name": "meeting_count", "label": "Jumlah sesi rapat", "type": "number", "default": 1},
                    {"name": "has_speaker", "label": "Ada narasumber", "type": "checkbox", "default": True},
                    {"name": "speaker_count", "label": "Jumlah narasumber", "type": "number", "default": 1},
                    {"name": "include_atk", "label": "Tambahkan ATK", "type": "checkbox", "default": True},
                    {"name": "include_supplies", "label": "Tambahkan suplai komputer", "type": "checkbox", "default": True},
                ],
                ensure_ascii=True,
            ),
        },
        {
            "code": "OUT_OF_TOWN_IDENTIFICATION",
            "name": "Identifikasi awal ke pabrik luar kota",
            "description": "Perjalanan dinas luar kota dengan opsi pesawat atau transport darat, hotel, dan uang harian.",
            "category": "lapangan",
            "parameter_schema_json": json.dumps(
                [
                    {"name": "province", "label": "Provinsi tujuan", "type": "select", "reference_key": "provinces", "default": "ACEH"},
                    {
                        "name": "origin_city",
                        "label": "Kota asal",
                        "type": "select",
                        "reference_key": "cities_by_province",
                        "province_source": "activity_default_province",
                        "default": "JAKARTA",
                    },
                    {
                        "name": "destination_city",
                        "label": "Kota tujuan",
                        "type": "select",
                        "reference_key": "cities_by_province",
                        "province_source_field": "province",
                        "default": "BANDA ACEH",
                    },
                    {
                        "name": "travel_mode",
                        "label": "Moda perjalanan utama",
                        "type": "select",
                        "default": "plane",
                        "options": [
                            {"value": "plane", "label": "Pesawat"},
                            {"value": "land", "label": "Transport darat"},
                        ],
                    },
                    {"name": "identification_count", "label": "Jumlah pelaksanaan identifikasi", "type": "number", "default": 1},
                    {"name": "traveler_count", "label": "Jumlah pegawai", "type": "number", "default": 2},
                    {"name": "trip_days", "label": "Jumlah hari", "type": "number", "default": 3},
                    {"name": "hotel_nights", "label": "Jumlah malam hotel", "type": "number", "default": 2},
                    {
                        "name": "hotel_grade",
                        "label": "Golongan hotel",
                        "type": "select",
                        "default": "gol_iv",
                        "options": [
                            {"value": "eselon_1", "label": "Eselon I"},
                            {"value": "eselon_2", "label": "Eselon II"},
                            {"value": "gol_iv", "label": "Eselon III / Golongan IV"},
                            {"value": "gol_iii", "label": "Eselon IV / Golongan III ke bawah"},
                        ],
                    },
                    {
                        "name": "flight_class",
                        "label": "Kelas pesawat",
                        "type": "select",
                        "default": "economy",
                        "options": [
                            {"value": "economy", "label": "Ekonomi"},
                            {"value": "business", "label": "Bisnis"},
                        ],
                    },
                ],
                ensure_ascii=True,
            ),
        },
        {
            "code": "ATTEND_EXTERNAL_MEETING",
            "name": "Menghadiri rapat instansi lain",
            "description": "Pilih cakupan perjalanan dalam kota atau luar kota untuk memunculkan akun 524114 atau 524119.",
            "category": "koordinasi_eksternal",
            "parameter_schema_json": json.dumps(
                [
                    {
                        "name": "travel_scope",
                        "label": "Cakupan perjalanan",
                        "type": "select",
                        "default": "within_city",
                        "options": [
                            {"value": "within_city", "label": "Dalam kota"},
                            {"value": "out_of_town", "label": "Luar kota"},
                        ],
                    },
                    {
                        "name": "province",
                        "label": "Provinsi tujuan",
                        "type": "select",
                        "reference_key": "provinces",
                        "default": "DKI JAKARTA",
                        "visible_when": {"travel_scope": "out_of_town"},
                    },
                    {
                        "name": "origin_city",
                        "label": "Kota asal",
                        "type": "select",
                        "reference_key": "cities_by_province",
                        "province_source": "activity_default_province",
                        "default": "JAKARTA",
                        "visible_when": {"travel_scope": "out_of_town"},
                    },
                    {
                        "name": "destination_city",
                        "label": "Kota tujuan",
                        "type": "select",
                        "reference_key": "cities_by_province",
                        "province_source_field": "province",
                        "default": "JAKARTA",
                        "visible_when": {"travel_scope": "out_of_town"},
                    },
                    {"name": "traveler_count", "label": "Jumlah pegawai", "type": "number", "default": 3},
                    {"name": "trip_days", "label": "Jumlah hari / kali rapat", "type": "number", "default": 1},
                    {
                        "name": "hotel_nights",
                        "label": "Jumlah malam hotel",
                        "type": "number",
                        "default": 0,
                        "visible_when": {"travel_scope": "out_of_town"},
                    },
                    {
                        "name": "travel_mode",
                        "label": "Moda perjalanan utama",
                        "type": "select",
                        "default": "plane",
                        "options": [
                            {"value": "plane", "label": "Pesawat"},
                            {"value": "land", "label": "Transport darat"},
                        ],
                        "visible_when": {"travel_scope": "out_of_town"},
                    },
                    {
                        "name": "hotel_grade",
                        "label": "Golongan hotel",
                        "type": "select",
                        "default": "gol_iv",
                        "options": [
                            {"value": "eselon_1", "label": "Eselon I"},
                            {"value": "eselon_2", "label": "Eselon II"},
                            {"value": "gol_iv", "label": "Eselon III / Golongan IV"},
                            {"value": "gol_iii", "label": "Eselon IV / Golongan III ke bawah"},
                        ],
                        "visible_when": {"travel_scope": "out_of_town"},
                    },
                    {
                        "name": "flight_class",
                        "label": "Kelas pesawat",
                        "type": "select",
                        "default": "economy",
                        "options": [
                            {"value": "economy", "label": "Ekonomi"},
                            {"value": "business", "label": "Bisnis"},
                        ],
                        "visible_when": {"travel_scope": "out_of_town"},
                    },
                ],
                ensure_ascii=True,
            ),
        },
        {
            "code": "LOCAL_FACTORY_VISIT",
            "name": "Kunjungan pabrik lokal dalam kota",
            "description": "Perjalanan dinas dalam kota dengan transport lokal dan uang harian.",
            "category": "lapangan_lokal",
            "parameter_schema_json": json.dumps(
                [
                    {"name": "province", "label": "Provinsi lokasi", "type": "select", "reference_key": "provinces", "default": "DKI JAKARTA"},
                    {"name": "traveler_count", "label": "Jumlah pegawai", "type": "number", "default": 4},
                    {"name": "trip_days", "label": "Jumlah hari", "type": "number", "default": 1},
                    {"name": "local_transport_budget", "label": "Estimasi transport lokal per orang", "type": "number", "default": 150000},
                ],
                ensure_ascii=True,
            ),
        },
        {
            "code": "TECHNICAL_GUIDANCE",
            "name": "Bimbingan teknis / workshop SDM",
            "description": "Digunakan untuk bimbingan teknis dan sesi berbagi materi internal/eksternal.",
            "category": "capacity_building",
            "parameter_schema_json": json.dumps(
                [
                    {"name": "province", "label": "Provinsi lokasi", "type": "select", "reference_key": "provinces", "default": "JAWA BARAT"},
                    {"name": "participant_count", "label": "Jumlah peserta", "type": "number", "default": 30},
                    {"name": "meeting_count", "label": "Jumlah sesi", "type": "number", "default": 2},
                    {"name": "has_speaker", "label": "Ada narasumber", "type": "checkbox", "default": True},
                    {"name": "speaker_count", "label": "Jumlah narasumber", "type": "number", "default": 2},
                    {
                        "name": "meeting_package_type",
                        "label": "Paket pertemuan",
                        "type": "select",
                        "default": "fullday",
                        "options": [
                            {"value": "halfdays", "label": "Halfday"},
                            {"value": "fullday", "label": "Fullday"},
                            {"value": "fullboard", "label": "Fullboard"},
                        ],
                    },
                ],
                ensure_ascii=True,
            ),
        },
    ]


def _budget_account_catalog() -> list[dict[str, Any]]:
    return [
        {
            "code": "521211",
            "name": "Belanja Bahan untuk Konsumsi Rapat, ATK, dan Suplai",
            "category": "barang",
            "description": "Akun yang disarankan untuk rapat di kantor, konsumsi rapat, dan dukungan bahan kegiatan.",
            "default_source_sheet": "KONSUM",
        },
        {
            "code": "522151",
            "name": "Belanja Jasa Profesi / Honor Narasumber",
            "category": "jasa",
            "description": "Digunakan untuk honor narasumber, moderator, atau tenaga ahli sesuai kebutuhan kegiatan.",
            "default_source_sheet": "HONOR",
        },
        {
            "code": "524111",
            "name": "Belanja Perjalanan Dinas Biasa",
            "category": "perjalanan",
            "description": "Mendukung tiket, hotel, taksi bandara, dan uang harian untuk identifikasi luar kota.",
            "default_source_sheet": "PESAWAT DN",
        },
        {
            "code": "524113",
            "name": "Belanja Perjalanan Dinas Dalam Kota",
            "category": "perjalanan",
            "description": "Digunakan untuk kunjungan lokal dalam kota dengan transport lokal dan uang harian.",
            "default_source_sheet": "UH DN",
        },
        {
            "code": "524114",
            "name": "Belanja Perjalanan Menghadiri Pertemuan Dalam Kota",
            "category": "perjalanan",
            "description": "Digunakan saat pegawai menghadiri rapat instansi lain dalam kota.",
            "default_source_sheet": "TAKSI BANDARA",
        },
        {
            "code": "524119",
            "name": "Belanja Perjalanan Menghadiri Pertemuan Luar Kota",
            "category": "perjalanan",
            "description": "Digunakan saat pegawai menghadiri rapat instansi lain luar kota.",
            "default_source_sheet": "PESAWAT DN",
        },
    ]


def _rule_catalog() -> list[dict[str, Any]]:
    return [
        {
            "id": "rule_office_meeting_base",
            "form_code": "OFFICE_MEETING",
            "rule_name": "Rapat kantor memerlukan konsumsi dan bahan rapat",
            "condition_json": json.dumps({}, ensure_ascii=True),
            "account_code": "521211",
            "recommended_reason": "Rapat kantor menampilkan konsumsi rapat, ATK, dan suplai komputer pada akun 521211.",
            "default_selected": 1,
            "sort_order": 10,
        },
        {
            "id": "rule_office_meeting_speaker",
            "form_code": "OFFICE_MEETING",
            "rule_name": "Honor narasumber untuk rapat kantor",
            "condition_json": json.dumps({"has_speaker": True}, ensure_ascii=True),
            "account_code": "522151",
            "recommended_reason": "Ada narasumber, sehingga akun 522151 direkomendasikan untuk honorarium jasa profesi.",
            "default_selected": 1,
            "sort_order": 20,
        },
        {
            "id": "rule_identification_out_of_town",
            "form_code": "OUT_OF_TOWN_IDENTIFICATION",
            "rule_name": "Identifikasi ke pabrik luar kota",
            "condition_json": json.dumps({}, ensure_ascii=True),
            "account_code": "524111",
            "recommended_reason": "Identifikasi awal ke pabrik luar kota menampilkan akun 524111 untuk perjalanan dinas biasa.",
            "default_selected": 1,
            "sort_order": 30,
        },
        {
            "id": "rule_external_meeting_within_city",
            "form_code": "ATTEND_EXTERNAL_MEETING",
            "rule_name": "Rapat instansi lain dalam kota",
            "condition_json": json.dumps({"travel_scope": "within_city"}, ensure_ascii=True),
            "account_code": "524114",
            "recommended_reason": "Menghadiri rapat instansi lain dalam kota merekomendasikan akun 524114 dengan detail transport lokal.",
            "default_selected": 1,
            "sort_order": 40,
        },
        {
            "id": "rule_external_meeting_out_of_town",
            "form_code": "ATTEND_EXTERNAL_MEETING",
            "rule_name": "Rapat instansi lain luar kota",
            "condition_json": json.dumps({"travel_scope": "out_of_town"}, ensure_ascii=True),
            "account_code": "524119",
            "recommended_reason": "Menghadiri rapat instansi lain luar kota merekomendasikan akun 524119 dengan detail perjalanan penuh.",
            "default_selected": 1,
            "sort_order": 50,
        },
        {
            "id": "rule_local_factory_visit",
            "form_code": "LOCAL_FACTORY_VISIT",
            "rule_name": "Kunjungan pabrik lokal dalam kota",
            "condition_json": json.dumps({}, ensure_ascii=True),
            "account_code": "524113",
            "recommended_reason": "Kunjungan pabrik lokal dalam kota menampilkan akun 524113 untuk transport lokal dan uang harian.",
            "default_selected": 1,
            "sort_order": 60,
        },
        {
            "id": "rule_technical_guidance_base",
            "form_code": "TECHNICAL_GUIDANCE",
            "rule_name": "Bimbingan teknis memerlukan konsumsi peserta",
            "condition_json": json.dumps({}, ensure_ascii=True),
            "account_code": "521211",
            "recommended_reason": "Bimbingan teknis memerlukan konsumsi peserta dan kebutuhan bahan kegiatan pada akun 521211.",
            "default_selected": 1,
            "sort_order": 70,
        },
        {
            "id": "rule_technical_guidance_speaker",
            "form_code": "TECHNICAL_GUIDANCE",
            "rule_name": "Bimbingan teknis dengan narasumber",
            "condition_json": json.dumps({"has_speaker": True}, ensure_ascii=True),
            "account_code": "522151",
            "recommended_reason": "Ada narasumber pada bimbingan teknis, sehingga akun 522151 direkomendasikan.",
            "default_selected": 1,
            "sort_order": 80,
        },
    ]


def _detail_template_catalog() -> list[dict[str, Any]]:
    return [
        {
            "id": "tpl_521211_consumption",
            "account_code": "521211",
            "item_name": "Konsumsi rapat",
            "default_unit": "Orang/Kali",
            "reference_key": "consumption_combined_regular",
            "metadata_json": json.dumps({"volume_source": "participant_meetings"}),
            "sort_order": 10,
        },
        {
            "id": "tpl_521211_atk",
            "account_code": "521211",
            "item_name": "ATK rapat",
            "default_unit": "Paket",
            "reference_key": "manual",
            "metadata_json": json.dumps({"volume_source": "single", "enabled_when": {"include_atk": True}, "fallback_price": 350000}),
            "sort_order": 20,
        },
        {
            "id": "tpl_521211_supplies",
            "account_code": "521211",
            "item_name": "Suplai komputer",
            "default_unit": "Paket",
            "reference_key": "manual",
            "metadata_json": json.dumps({"volume_source": "single", "enabled_when": {"include_supplies": True}, "fallback_price": 500000}),
            "sort_order": 30,
        },
        {
            "id": "tpl_522151_honor_narasumber",
            "account_code": "522151",
            "item_name": "Honorarium Narasumber",
            "default_unit": "OJ",
            "reference_key": "honor_narasumber",
            "metadata_json": json.dumps({"volume_source": "speaker_count"}),
            "sort_order": 10,
        },
        {
            "id": "tpl_524111_flight",
            "account_code": "524111",
            "item_name": "Tiket pesawat perjalanan dinas PP",
            "default_unit": "Orang",
            "reference_key": "flight_domestic",
            "metadata_json": json.dumps({"volume_source": "traveler_count", "enabled_when": {"travel_mode": "plane"}}),
            "sort_order": 10,
        },
        {
            "id": "tpl_524111_land",
            "account_code": "524111",
            "item_name": "Transportasi darat utama",
            "default_unit": "Orang/Kali",
            "reference_key": "land_transport_domestic",
            "metadata_json": json.dumps({"volume_source": "traveler_count", "enabled_when": {"travel_mode": "land"}, "fallback_price": 250000}),
            "sort_order": 20,
        },
        {
            "id": "tpl_524111_taxi",
            "account_code": "524111",
            "item_name": "Taksi bandara",
            "default_unit": "Orang/Kali",
            "reference_key": "airport_taxi_domestic",
            "metadata_json": json.dumps({"volume_source": "traveler_count_x_two", "enabled_when": {"travel_mode": "plane"}}),
            "sort_order": 30,
        },
        {
            "id": "tpl_524111_hotel",
            "account_code": "524111",
            "item_name": "Hotel",
            "default_unit": "OH",
            "reference_key": "hotel_domestic",
            "metadata_json": json.dumps({"volume_source": "hotel_nights"}),
            "sort_order": 40,
        },
        {
            "id": "tpl_524111_daily",
            "account_code": "524111",
            "item_name": "Uang harian",
            "default_unit": "OH",
            "reference_key": "daily_allowance_out_town",
            "metadata_json": json.dumps({"volume_source": "trip_days"}),
            "sort_order": 50,
        },
        {
            "id": "tpl_524113_local_transport",
            "account_code": "524113",
            "item_name": "Transport lokal",
            "default_unit": "Orang/Kali",
            "reference_key": "manual_local_transport",
            "metadata_json": json.dumps({"volume_source": "traveler_count", "fallback_context_key": "local_transport_budget", "fallback_price": 150000}),
            "sort_order": 10,
        },
        {
            "id": "tpl_524113_daily",
            "account_code": "524113",
            "item_name": "Uang harian",
            "default_unit": "OH",
            "reference_key": "daily_allowance_in_town",
            "metadata_json": json.dumps({"volume_source": "trip_days"}),
            "sort_order": 20,
        },
        {
            "id": "tpl_524114_local_transport",
            "account_code": "524114",
            "item_name": "Transport kegiatan dalam kabupaten/kota PP",
            "default_unit": "Orang/Kali",
            "reference_key": "local_transport_activity_pp",
            "metadata_json": json.dumps({"volume_source": "trip_days", "fallback_price": 170000}),
            "sort_order": 10,
        },
        {
            "id": "tpl_524119_flight",
            "account_code": "524119",
            "item_name": "Tiket pesawat perjalanan dinas PP",
            "default_unit": "Orang",
            "reference_key": "flight_domestic",
            "metadata_json": json.dumps({"volume_source": "traveler_count", "enabled_when": {"travel_mode": "plane"}}),
            "sort_order": 10,
        },
        {
            "id": "tpl_524119_land",
            "account_code": "524119",
            "item_name": "Transportasi darat utama",
            "default_unit": "Orang/Kali",
            "reference_key": "land_transport_domestic",
            "metadata_json": json.dumps({"volume_source": "traveler_count", "enabled_when": {"travel_mode": "land"}, "fallback_price": 250000}),
            "sort_order": 20,
        },
        {
            "id": "tpl_524119_taxi",
            "account_code": "524119",
            "item_name": "Taksi bandara",
            "default_unit": "Orang/Kali",
            "reference_key": "airport_taxi_domestic",
            "metadata_json": json.dumps({"volume_source": "traveler_count_x_two", "enabled_when": {"travel_mode": "plane"}}),
            "sort_order": 30,
        },
        {
            "id": "tpl_524119_hotel",
            "account_code": "524119",
            "item_name": "Hotel",
            "default_unit": "OH",
            "reference_key": "hotel_domestic",
            "metadata_json": json.dumps({"volume_source": "hotel_nights"}),
            "sort_order": 40,
        },
        {
            "id": "tpl_524119_daily",
            "account_code": "524119",
            "item_name": "Uang harian",
            "default_unit": "OH",
            "reference_key": "daily_allowance_out_town",
            "metadata_json": json.dumps({"volume_source": "trip_days"}),
            "sort_order": 50,
        },
    ]


def seed_reference_catalog(connection: sqlite3.Connection) -> None:
    form_catalog = _activity_form_catalog()
    account_catalog = _budget_account_catalog()
    rule_catalog = _rule_catalog()
    template_catalog = _detail_template_catalog()
    connection.executemany(
        """
        INSERT INTO activity_forms (code, name, description, category, parameter_schema_json, is_active)
        VALUES (:code, :name, :description, :category, :parameter_schema_json, 1)
        ON CONFLICT(code) DO UPDATE SET
            name = excluded.name,
            description = excluded.description,
            category = excluded.category,
            parameter_schema_json = excluded.parameter_schema_json,
            is_active = excluded.is_active
        """,
        form_catalog,
    )
    connection.executemany(
        """
        INSERT INTO budget_accounts (code, name, category, description, default_source_sheet)
        VALUES (:code, :name, :category, :description, :default_source_sheet)
        ON CONFLICT(code) DO UPDATE SET
            name = excluded.name,
            category = excluded.category,
            description = excluded.description,
            default_source_sheet = excluded.default_source_sheet
        """,
        account_catalog,
    )
    connection.executemany(
        """
        INSERT INTO account_rules (
            id, form_code, rule_name, condition_json, account_code, recommended_reason, default_selected, sort_order
        )
        VALUES (
            :id, :form_code, :rule_name, :condition_json, :account_code, :recommended_reason, :default_selected, :sort_order
        )
        ON CONFLICT(id) DO UPDATE SET
            form_code = excluded.form_code,
            rule_name = excluded.rule_name,
            condition_json = excluded.condition_json,
            account_code = excluded.account_code,
            recommended_reason = excluded.recommended_reason,
            default_selected = excluded.default_selected,
            sort_order = excluded.sort_order
        """,
        rule_catalog,
    )
    connection.executemany(
        """
        INSERT INTO account_detail_templates (
            id, account_code, item_name, default_unit, reference_key, metadata_json, sort_order
        )
        VALUES (:id, :account_code, :item_name, :default_unit, :reference_key, :metadata_json, :sort_order)
        ON CONFLICT(id) DO UPDATE SET
            account_code = excluded.account_code,
            item_name = excluded.item_name,
            default_unit = excluded.default_unit,
            reference_key = excluded.reference_key,
            metadata_json = excluded.metadata_json,
            sort_order = excluded.sort_order
        """,
        template_catalog,
    )
    active_form_codes = [item["code"] for item in form_catalog]
    if active_form_codes:
        placeholders = ",".join("?" for _ in active_form_codes)
        connection.execute(
            f"UPDATE activity_forms SET is_active = 0 WHERE code NOT IN ({placeholders})",
            active_form_codes,
        )

    rule_ids = [item["id"] for item in rule_catalog]
    if rule_ids:
        placeholders = ",".join("?" for _ in rule_ids)
        connection.execute(
            f"DELETE FROM account_rules WHERE id NOT IN ({placeholders})",
            rule_ids,
        )

    template_ids = [item["id"] for item in template_catalog]
    if template_ids:
        placeholders = ",".join("?" for _ in template_ids)
        connection.execute(
            f"DELETE FROM account_detail_templates WHERE id NOT IN ({placeholders})",
            template_ids,
        )


def seed_cost_references(connection: sqlite3.Connection) -> dict[str, Any]:
    existing = connection.execute("SELECT COUNT(*) AS count FROM cost_references").fetchone()["count"]
    if existing:
        return {"source": "database", "records": existing}

    source = resolve_sbm_source()
    if source is not None:
        try:
            record_count = import_sbm_workbook(connection, source)
            return {"source": str(source), "records": record_count}
        except OSError as error:
            record_count = seed_fallback_costs(connection)
            return {"source": "fallback", "records": record_count, "warning": str(error)}

    record_count = seed_fallback_costs(connection)
    return {"source": "fallback", "records": record_count}


def bootstrap_sample_activity(connection: sqlite3.Connection) -> None:
    count = connection.execute("SELECT COUNT(*) AS count FROM activities").fetchone()["count"]
    if count:
        return

    activity_id = "activity_hilirisasi_kelapa"
    connection.execute(
        """
        INSERT INTO activities (id, name, description, fiscal_year, budget_ceiling, default_province, origin_city, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            activity_id,
            "Hilirisasi Kelapa",
            "Contoh kegiatan untuk menunjukkan workflow penyusunan RAB kegiatan kementerian berbasis tahapan.",
            2026,
            150000000,
            "DKI JAKARTA",
            "JAKARTA",
            _now(),
            _now(),
        ),
    )
    sub_components = [
        ("sub_persiapan", "A", 1, "Persiapan", "Koordinasi awal dan penyiapan kebutuhan kegiatan."),
        (
            "sub_identifikasi",
            "B",
            2,
            "Koordinasi dan Identifikasi Lapangan",
            "Identifikasi pabrik, koordinasi lapangan, dan validasi kebutuhan intervensi.",
        ),
        ("sub_bimtek", "C", 3, "Bimbingan Teknis SDM Industri Kelapa", "Pelatihan singkat untuk SDM industri."),
        ("sub_pelaksanaan_akhir", "D", 4, "Pelaksanaan Akhir", "Rapat tindak lanjut dan finalisasi output."),
    ]
    connection.executemany(
        """
        INSERT INTO sub_components (id, activity_id, code, name, sequence, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [(sub_id, activity_id, code, name, sequence, notes, _now(), _now()) for sub_id, code, sequence, name, notes in sub_components],
    )

    selections = [
        (
            "form_persiapan",
            "sub_persiapan",
            "OFFICE_MEETING",
            {
                "province": "DKI JAKARTA",
                "participant_count": 18,
                "meeting_count": 1,
                "has_speaker": True,
                "speaker_count": 2,
                "include_atk": True,
                "include_supplies": True,
            },
        ),
        (
            "form_identifikasi",
            "sub_identifikasi",
            "OUT_OF_TOWN_IDENTIFICATION",
            {
                "province": "ACEH",
                "origin_city": "JAKARTA",
                "destination_city": "BANDA ACEH",
                "travel_mode": "plane",
                "identification_count": 1,
                "traveler_count": 3,
                "trip_days": 3,
                "hotel_nights": 2,
                "hotel_grade": "gol_iv",
                "flight_class": "economy",
            },
        ),
        (
            "form_bimtek",
            "sub_bimtek",
            "TECHNICAL_GUIDANCE",
            {
                "province": "JAWA BARAT",
                "participant_count": 30,
                "meeting_count": 2,
                "has_speaker": True,
                "speaker_count": 2,
                "meeting_package_type": "fullday",
                "include_atk": True,
                "include_supplies": True,
            },
        ),
        (
            "form_pelaksanaan_akhir",
            "sub_pelaksanaan_akhir",
            "ATTEND_EXTERNAL_MEETING",
            {
                "travel_scope": "within_city",
                "traveler_count": 4,
                "trip_days": 1,
            },
        ),
    ]
    connection.executemany(
        """
        INSERT INTO activity_form_selections (id, sub_component_id, form_code, attributes_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [(selection_id, sub_id, form_code, json.dumps(attributes, ensure_ascii=True), _now(), _now()) for selection_id, sub_id, form_code, attributes in selections],
    )

    for sub_component_id in ["sub_persiapan", "sub_identifikasi", "sub_bimtek", "sub_pelaksanaan_akhir"]:
        apply_rules_for_sub_component(connection, sub_component_id)


def bootstrap_application_data(connection: sqlite3.Connection) -> dict[str, Any]:
    seed_reference_catalog(connection)
    cost_meta = seed_cost_references(connection)
    bootstrap_sample_activity(connection)
    return {"cost_meta": cost_meta}


def _city_label_lookup(connection: sqlite3.Connection) -> dict[str, str]:
    labels: dict[str, str] = {}
    for row in connection.execute(
        """
        SELECT origin AS value
        FROM cost_references
        WHERE origin IS NOT NULL
          AND trim(origin) <> ''
        UNION
        SELECT destination AS value
        FROM cost_references
        WHERE destination IS NOT NULL
          AND trim(destination) <> ''
        ORDER BY value
        """
    ).fetchall():
        if not _is_valid_location_value(row["value"], "city"):
            continue
        city = _clean_location_text(row["value"])
        city_key = normalize_key(city)
        if city_key and city_key not in labels:
            labels[city_key] = city
    return labels


def _province_city_registry(connection: sqlite3.Connection) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    city_labels = _city_label_lookup(connection)
    province_to_cities: dict[str, dict[str, str]] = defaultdict(dict)
    city_to_province: dict[str, str] = {}

    for row in connection.execute(
        """
        SELECT region, origin, destination
        FROM cost_references
        WHERE category = 'land_transport_domestic'
          AND region IS NOT NULL
          AND trim(region) <> ''
        ORDER BY region, origin, destination
        """
    ).fetchall():
        province = _clean_location_text(row["region"])
        if not _is_valid_location_value(province, "province"):
            continue
        for city_value in [row["origin"], row["destination"]]:
            if not _is_valid_location_value(city_value, "city"):
                continue
            city_key = normalize_key(_clean_location_text(city_value))
            city = city_labels.get(city_key, _clean_location_text(city_value))
            province_to_cities[province][city_key] = city
            city_to_province.setdefault(city_key, province)

    for city_key, province in CITY_PROVINCE_OVERRIDES.items():
        city = city_labels.get(city_key)
        if not city:
            continue
        province_name = _clean_location_text(province)
        province_to_cities[province_name][city_key] = city
        city_to_province[city_key] = province_name

    return province_to_cities, city_to_province


def _build_location_reference(connection: sqlite3.Connection) -> dict[str, Any]:
    placeholders = ",".join("?" for _ in PROVINCE_REFERENCE_CATEGORIES)
    province_values = [
        row["value"]
        for row in connection.execute(
            f"""
            SELECT DISTINCT region AS value
            FROM cost_references
            WHERE category IN ({placeholders})
              AND region IS NOT NULL
              AND trim(region) <> ''
            ORDER BY region
            """,
            PROVINCE_REFERENCE_CATEGORIES,
        ).fetchall()
        if _is_valid_location_value(row["value"], "province")
    ]
    city_labels = _city_label_lookup(connection)
    province_to_cities, city_to_province = _province_city_registry(connection)
    provinces = _sorted_unique_strings(province_values + list(province_to_cities.keys()))
    cities = _sorted_unique_strings(list(city_labels.values()))
    cities_by_province = {
        province: _sorted_unique_strings(list(city_map.values()))
        for province, city_map in sorted(province_to_cities.items(), key=lambda item: normalize_key(item[0]))
    }
    city_to_province_display = {
        city_labels.get(city_key, city_key): province
        for city_key, province in sorted(city_to_province.items(), key=lambda item: normalize_key(city_labels.get(item[0], item[0])))
    }
    return {
        "provinces": provinces,
        "cities": cities,
        "cities_by_province": cities_by_province,
        "city_to_province": city_to_province_display,
    }


def list_reference_data(connection: sqlite3.Connection) -> dict[str, Any]:
    forms = [
        {
            **_row_to_dict(row),
            "parameter_schema": _json_loads(row["parameter_schema_json"], []),
        }
        for row in connection.execute("SELECT * FROM activity_forms WHERE is_active = 1 ORDER BY name")
    ]
    accounts = [_row_to_dict(row) for row in connection.execute("SELECT * FROM budget_accounts ORDER BY code")]
    return {
        "forms": forms,
        "accounts": accounts,
        "locations": _build_location_reference(connection),
    }


def _condition_matches(attributes: dict[str, Any], condition: dict[str, Any]) -> bool:
    for key, expected in condition.items():
        actual = attributes.get(key)
        if isinstance(expected, list):
            if actual not in expected:
                return False
            continue
        if isinstance(expected, bool):
            if _to_bool(actual) != expected:
                return False
            continue
        if actual != expected:
            return False
    return True


def _enabled_for_context(metadata: dict[str, Any], context: dict[str, Any]) -> bool:
    enabled_when = metadata.get("enabled_when", {})
    return _condition_matches(context, enabled_when)


def _derive_volume(metadata: dict[str, Any], context: dict[str, Any]) -> float:
    source = metadata.get("volume_source", "single")
    participant_count = _to_float(context.get("participant_count"), 0)
    meeting_count = _to_float(context.get("meeting_count"), 1)
    speaker_count = _to_float(context.get("speaker_count"), 0)
    traveler_count = _to_float(context.get("traveler_count"), 1)
    trip_days = _to_float(context.get("trip_days"), 1)
    hotel_nights = _to_float(context.get("hotel_nights"), 0)
    identification_count = _to_float(context.get("identification_count"), 1)
    travel_multiplier = max(identification_count, 1)

    lookup = {
        "single": 1,
        "participant_count": participant_count,
        "participant_meetings": participant_count * max(meeting_count, 1),
        "speaker_count": max(speaker_count, 1),
        "traveler_count": max(traveler_count, 1) * travel_multiplier,
        "traveler_count_x_two": max(traveler_count, 1) * 2 * travel_multiplier,
        "trip_days": max(traveler_count, 1) * max(trip_days, 1) * travel_multiplier,
        "hotel_nights": max(traveler_count, 1) * max(hotel_nights, 0) * travel_multiplier,
    }
    return float(lookup.get(source, 1))


def _province_for_city(
    connection: sqlite3.Connection,
    city: str | None,
    fallback_province: str | None = None,
) -> str | None:
    city_key = normalize_key(_clean_location_text(city))
    if city_key:
        override = CITY_PROVINCE_OVERRIDES.get(city_key)
        if override:
            return _clean_location_text(override)

        row = connection.execute(
            """
            SELECT region
            FROM cost_references
            WHERE category = 'land_transport_domestic'
              AND (origin_key = ? OR destination_key = ?)
              AND region IS NOT NULL
              AND trim(region) <> ''
            LIMIT 1
            """,
            (city_key, city_key),
        ).fetchone()
        if row and _is_valid_location_value(row["region"], "province"):
            return _clean_location_text(row["region"])

    if fallback_province:
        return _clean_location_text(fallback_province)
    return None


def _reference_lookup(
    connection: sqlite3.Connection,
    *,
    category: str,
    region: str | None = None,
    origin: str | None = None,
    destination: str | None = None,
    label: str | None = None,
) -> sqlite3.Row | None:
    if label:
        return connection.execute(
            "SELECT * FROM cost_references WHERE category = ? AND upper(label) = upper(?) LIMIT 1",
            (category, label),
        ).fetchone()
    if origin or destination:
        return connection.execute(
            """
            SELECT * FROM cost_references
            WHERE category = ?
              AND origin_key = ?
              AND destination_key = ?
            LIMIT 1
            """,
            (category, normalize_key(origin), normalize_key(destination)),
        ).fetchone()
    return connection.execute(
        """
        SELECT * FROM cost_references
        WHERE category = ?
          AND region_key = ?
        LIMIT 1
        """,
        (category, normalize_key(region)),
    ).fetchone()


def _pricing_suggestion(
    connection: sqlite3.Connection,
    reference_key: str,
    context: dict[str, Any],
    metadata: dict[str, Any],
) -> tuple[float, str]:
    province = context.get("province") or "DKI JAKARTA"
    origin_city = context.get("origin_city") or "JAKARTA"
    destination_city = context.get("destination_city") or context.get("province") or "JAKARTA"
    flight_class = context.get("flight_class") or "economy"
    hotel_grade = context.get("hotel_grade") or "gol_iv"
    fallback_price = _to_float(context.get(metadata.get("fallback_context_key")), _to_float(metadata.get("fallback_price"), 0))

    if reference_key == "manual":
        return fallback_price, "Harga awal disiapkan manual dan masih bisa diubah."

    if reference_key == "manual_local_transport":
        return fallback_price, "Transport lokal belum memiliki lookup SBM yang seragam, sehingga dimulai dari estimasi manual."

    if reference_key == "local_transport_activity_pp":
        row = _reference_lookup(connection, category="local_transport_activity_pp", label="Transport kegiatan dalam kabupaten/kota PP")
        if row:
            return _to_float(row["rate_primary"]), "Transport kegiatan dalam kabupaten/kota PP mengacu ke sheet TRANS DARAT."
        return fallback_price, "Tarif transport kegiatan dalam kabupaten/kota PP belum tersedia, gunakan input manual."

    if reference_key == "honor_narasumber":
        row = _reference_lookup(connection, category="honorarium", label="Honorarium Narasumber")
        if row:
            return _to_float(row["rate_primary"]), "Tarif honor narasumber mengacu ke sheet HONOR pada file SBM."
        return fallback_price, "Tarif honor narasumber tidak ditemukan, gunakan input manual."

    if reference_key == "consumption_combined_regular":
        row = _reference_lookup(connection, category="consumption_regular", region=province)
        if row:
            total_rate = _to_float(row["rate_primary"]) + _to_float(row["rate_secondary"])
            return total_rate, f"Tarif konsumsi rapat menggabungkan makan dan kudapan dari sheet KONSUM untuk provinsi {province}."
        return fallback_price, f"Tarif konsumsi rapat provinsi {province} belum tersedia, gunakan input manual."

    if reference_key == "daily_allowance_out_town":
        row = _reference_lookup(connection, category="daily_allowance_domestic", region=province)
        if row:
            return _to_float(row["rate_primary"]), f"Uang harian luar kota mengacu ke sheet UH DN untuk provinsi {province}."
        return fallback_price, f"Uang harian luar kota provinsi {province} belum tersedia, gunakan input manual."

    if reference_key == "daily_allowance_in_town":
        row = _reference_lookup(connection, category="daily_allowance_domestic", region=province)
        if row:
            return _to_float(row["rate_secondary"]), f"Uang harian dalam kota mengacu ke sheet UH DN untuk provinsi {province}."
        return fallback_price, f"Uang harian dalam kota provinsi {province} belum tersedia, gunakan input manual."

    if reference_key == "hotel_domestic":
        row = _reference_lookup(connection, category="hotel_domestic", region=province)
        if row:
            mapping = {
                "eselon_1": _to_float(row["rate_primary"]),
                "eselon_2": _to_float(row["rate_secondary"]),
                "gol_iv": _to_float(row["rate_tertiary"]),
                "gol_iii": _to_float(row["rate_quaternary"]),
            }
            return mapping.get(hotel_grade, mapping["gol_iv"]), f"Tarif hotel mengacu ke sheet HOTEL untuk provinsi {province}."
        return fallback_price, f"Tarif hotel provinsi {province} belum tersedia, gunakan input manual."

    if reference_key == "airport_taxi_domestic":
        taxi_province = _province_for_city(connection, origin_city, province) or province
        row = _reference_lookup(connection, category="airport_taxi_domestic", region=taxi_province)
        if row:
            return _to_float(row["rate_primary"]), f"Tarif taksi bandara mengacu ke sheet TAKSI BANDARA berdasarkan kota asal {origin_city} di provinsi {taxi_province}."
        return fallback_price, f"Tarif taksi bandara untuk kota asal {origin_city} belum tersedia, gunakan input manual."

    if reference_key == "flight_domestic":
        row = _reference_lookup(
            connection,
            category="flight_domestic_pp",
            origin=origin_city,
            destination=destination_city,
        )
        if row:
            if str(flight_class).lower() == "business":
                return _to_float(row["rate_primary"]), f"Tarif tiket kelas bisnis mengacu ke sheet PESAWAT DN rute {origin_city} - {destination_city}."
            return _to_float(row["rate_secondary"]), f"Tarif tiket kelas ekonomi mengacu ke sheet PESAWAT DN rute {origin_city} - {destination_city}."
        return fallback_price, f"Tarif tiket {origin_city} - {destination_city} belum tersedia, gunakan input manual."

    if reference_key == "land_transport_domestic":
        row = _reference_lookup(
            connection,
            category="land_transport_domestic",
            origin=origin_city,
            destination=destination_city,
        )
        if row:
            return _to_float(row["rate_primary"]), f"Transport darat mengacu ke sheet TRANS DARAT rute {origin_city} - {destination_city}."
        return fallback_price, f"Tarif transport darat {origin_city} - {destination_city} belum tersedia, gunakan input manual."

    return fallback_price, "Belum ada referensi otomatis, harga dimulai dari nilai manual."


def _context_for_form(
    connection: sqlite3.Connection,
    sub_component_id: str,
    form_selection_id: str | None = None,
) -> tuple[dict[str, Any], sqlite3.Row | None]:
    sub_row = connection.execute(
        """
        SELECT sub_components.*, activities.default_province, activities.origin_city
        FROM sub_components
        JOIN activities ON activities.id = sub_components.activity_id
        WHERE sub_components.id = ?
        """,
        (sub_component_id,),
    ).fetchone()
    if sub_row is None:
        return {}, None

    form_row = None
    if form_selection_id:
        form_row = connection.execute(
            "SELECT * FROM activity_form_selections WHERE id = ?",
            (form_selection_id,),
        ).fetchone()
    if form_row is None:
        form_row = connection.execute(
            "SELECT * FROM activity_form_selections WHERE sub_component_id = ? ORDER BY created_at LIMIT 1",
            (sub_component_id,),
        ).fetchone()

    attributes = _json_loads(form_row["attributes_json"], {}) if form_row else {}
    context = {
        "province": attributes.get("province") or sub_row["default_province"] or "DKI JAKARTA",
        "origin_city": attributes.get("origin_city") or sub_row["origin_city"] or "JAKARTA",
        "destination_city": attributes.get("destination_city") or attributes.get("province") or sub_row["default_province"] or "JAKARTA",
        "participant_count": _to_float(attributes.get("participant_count"), 0),
        "meeting_count": _to_float(attributes.get("meeting_count"), 1),
        "has_speaker": _to_bool(attributes.get("has_speaker")),
        "speaker_count": _to_float(attributes.get("speaker_count"), 0),
        "include_atk": _to_bool(attributes.get("include_atk")) if "include_atk" in attributes else True,
        "include_supplies": _to_bool(attributes.get("include_supplies")) if "include_supplies" in attributes else True,
        "travel_scope": attributes.get("travel_scope") or "within_city",
        "travel_mode": attributes.get("travel_mode") or "plane",
        "identification_count": _to_float(attributes.get("identification_count"), 1),
        "traveler_count": _to_float(attributes.get("traveler_count"), 1),
        "trip_days": _to_float(attributes.get("trip_days"), 1),
        "hotel_nights": _to_float(attributes.get("hotel_nights"), 0),
        "hotel_grade": attributes.get("hotel_grade") or "gol_iv",
        "flight_class": attributes.get("flight_class") or "economy",
        "local_transport_budget": _to_float(attributes.get("local_transport_budget"), 0),
        "meeting_package_type": attributes.get("meeting_package_type") or "fullday",
    }
    return context, form_row


def _ensure_default_lines(connection: sqlite3.Connection, account_selection_id: str) -> None:
    selection = connection.execute(
        "SELECT * FROM budget_account_selections WHERE id = ?",
        (account_selection_id,),
    ).fetchone()
    if selection is None:
        return

    templates = connection.execute(
        "SELECT * FROM account_detail_templates WHERE account_code = ? ORDER BY sort_order, item_name",
        (selection["account_code"],),
    ).fetchall()
    context, _ = _context_for_form(connection, selection["sub_component_id"], selection["form_selection_id"])
    template_payloads: list[tuple[sqlite3.Row, float, float, str]] = []
    enabled_template_ids: set[str] = set()
    for template in templates:
        metadata = _json_loads(template["metadata_json"], {})
        if not _enabled_for_context(metadata, context):
            continue
        volume = _derive_volume(metadata, context)
        suggestion_price, suggestion_note = _pricing_suggestion(connection, template["reference_key"], context, metadata)
        enabled_template_ids.add(template["id"])
        template_payloads.append((template, volume, suggestion_price, suggestion_note))

    existing_auto_rows = connection.execute(
        """
        SELECT *
        FROM budget_lines
        WHERE account_selection_id = ?
          AND is_manual = 0
        ORDER BY sort_order, created_at, id
        """,
        (account_selection_id,),
    ).fetchall()
    existing_by_template: dict[str | None, list[sqlite3.Row]] = defaultdict(list)
    for row in existing_auto_rows:
        existing_by_template[row["template_id"]].append(row)

    existing_primary_by_template: dict[str, sqlite3.Row] = {}
    for template_id, rows in existing_by_template.items():
        if not template_id or template_id not in enabled_template_ids:
            for row in rows:
                connection.execute("DELETE FROM budget_lines WHERE id = ?", (row["id"],))
            continue
        existing_primary_by_template[template_id] = rows[0]
        for duplicate in rows[1:]:
            connection.execute("DELETE FROM budget_lines WHERE id = ?", (duplicate["id"],))

    for template, volume, suggestion_price, suggestion_note in template_payloads:
        existing_row = existing_primary_by_template.get(template["id"])
        if existing_row is not None:
            previous_suggested = _to_float(existing_row["suggested_unit_price"], suggestion_price)
            current_unit_price = _to_float(existing_row["unit_price"], suggestion_price)
            unit_price = suggestion_price if abs(current_unit_price - previous_suggested) < 0.01 else current_unit_price
            connection.execute(
                """
                UPDATE budget_lines
                SET template_id = ?,
                    item_name = ?,
                    volume = ?,
                    unit = ?,
                    unit_price = ?,
                    suggested_unit_price = ?,
                    amount = ?,
                    suggestion_note = ?,
                    pricing_context_json = ?,
                    sort_order = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    template["id"],
                    template["item_name"],
                    volume,
                    template["default_unit"],
                    unit_price,
                    suggestion_price,
                    volume * unit_price,
                    suggestion_note,
                    json.dumps(context, ensure_ascii=True),
                    template["sort_order"],
                    _now(),
                    existing_row["id"],
                ),
            )
            continue

        connection.execute(
            """
            INSERT INTO budget_lines (
                id, account_selection_id, template_id, item_name, specification, volume, unit,
                unit_price, suggested_unit_price, amount, suggestion_note, pricing_context_json,
                is_manual, sort_order, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
            """,
            (
                _new_id("line"),
                account_selection_id,
                template["id"],
                template["item_name"],
                "",
                volume,
                template["default_unit"],
                suggestion_price,
                suggestion_price,
                volume * suggestion_price,
                suggestion_note,
                json.dumps(context, ensure_ascii=True),
                template["sort_order"],
                _now(),
                _now(),
            ),
        )


def apply_rules_for_sub_component(connection: sqlite3.Connection, sub_component_id: str) -> None:
    form_selections = connection.execute(
        "SELECT * FROM activity_form_selections WHERE sub_component_id = ? ORDER BY created_at, id",
        (sub_component_id,),
    ).fetchall()

    recommendations: dict[str, dict[str, Any]] = {}
    for form_selection in form_selections:
        attributes = _json_loads(form_selection["attributes_json"], {})
        rules = connection.execute(
            "SELECT * FROM account_rules WHERE form_code = ? ORDER BY sort_order, id",
            (form_selection["form_code"],),
        ).fetchall()
        for rule in rules:
            conditions = _json_loads(rule["condition_json"], {})
            if not _condition_matches(attributes, conditions):
                continue
            recommendation = recommendations.setdefault(
                rule["account_code"],
                {
                    "account_code": rule["account_code"],
                    "reason_parts": [],
                    "source_rule_id": rule["id"],
                    "form_selection_id": form_selection["id"],
                    "default_selected": bool(rule["default_selected"]),
                },
            )
            recommendation["reason_parts"].append(rule["recommended_reason"])
            recommendation["default_selected"] = recommendation["default_selected"] or bool(rule["default_selected"])

    existing_rows = connection.execute(
        """
        SELECT * FROM budget_account_selections
        WHERE sub_component_id = ?
        ORDER BY is_manual DESC, account_code
        """,
        (sub_component_id,),
    ).fetchall()
    existing = {(row["account_code"], row["is_manual"]): row for row in existing_rows}
    recommended_codes = set(recommendations.keys())

    for account_code, recommendation in recommendations.items():
        existing_row = existing.get((account_code, 0))
        reason_text = " ".join(dict.fromkeys(recommendation["reason_parts"]))
        if existing_row is None:
            selection_id = _new_id("account")
            connection.execute(
                """
                INSERT INTO budget_account_selections (
                    id, sub_component_id, form_selection_id, account_code, recommendation_reason,
                    source_rule_id, is_recommended, is_selected, is_manual, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 1, ?, 0, ?, ?)
                """,
                (
                    selection_id,
                    sub_component_id,
                    recommendation["form_selection_id"],
                    account_code,
                    reason_text,
                    recommendation["source_rule_id"],
                    1 if recommendation["default_selected"] else 0,
                    _now(),
                    _now(),
                ),
            )
            if recommendation["default_selected"]:
                _ensure_default_lines(connection, selection_id)
            continue

        connection.execute(
            """
            UPDATE budget_account_selections
            SET form_selection_id = ?,
                recommendation_reason = ?,
                source_rule_id = ?,
                is_recommended = 1,
                updated_at = ?
            WHERE id = ?
            """,
            (
                recommendation["form_selection_id"],
                reason_text,
                recommendation["source_rule_id"],
                _now(),
                existing_row["id"],
            ),
        )
        if existing_row["is_selected"]:
            _ensure_default_lines(connection, existing_row["id"])

    for row in existing_rows:
        if row["is_manual"]:
            if row["is_selected"]:
                _ensure_default_lines(connection, row["id"])
            continue
        if row["account_code"] in recommended_codes:
            continue
        line_count = connection.execute(
            "SELECT COUNT(*) AS count FROM budget_lines WHERE account_selection_id = ?",
            (row["id"],),
        ).fetchone()["count"]
        if line_count == 0 and not row["is_selected"]:
            connection.execute("DELETE FROM budget_account_selections WHERE id = ?", (row["id"],))
        else:
            connection.execute(
                """
                UPDATE budget_account_selections
                SET is_recommended = 0,
                    recommendation_reason = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                ("Akun dipertahankan, tetapi tidak lagi masuk rekomendasi aktif berdasarkan pilihan bentuk kegiatan saat ini.", _now(), row["id"]),
            )


def list_activities(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT * FROM activities ORDER BY updated_at DESC, created_at DESC"
    ).fetchall()
    activities: list[dict[str, Any]] = []
    for row in rows:
        activity = _row_to_dict(row)
        summary = activity_summary(connection, row["id"])
        activity["summary"] = summary
        activities.append(activity)
    return activities


def create_activity(connection: sqlite3.Connection, payload: ActivityPayload) -> dict[str, Any]:
    activity_id = _new_id("activity")
    connection.execute(
        """
        INSERT INTO activities (id, name, description, fiscal_year, budget_ceiling, default_province, origin_city, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            activity_id,
            payload.name,
            payload.description or "",
            payload.fiscal_year,
            payload.budget_ceiling,
            payload.default_province,
            payload.origin_city or "JAKARTA",
            _now(),
            _now(),
        ),
    )
    return get_activity_state(connection, activity_id)


def update_activity(connection: sqlite3.Connection, activity_id: str, payload: ActivityPayload) -> dict[str, Any]:
    connection.execute(
        """
        UPDATE activities
        SET name = ?, description = ?, fiscal_year = ?, budget_ceiling = ?, default_province = ?, origin_city = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            payload.name,
            payload.description or "",
            payload.fiscal_year,
            payload.budget_ceiling,
            payload.default_province,
            payload.origin_city or "JAKARTA",
            _now(),
            activity_id,
        ),
    )
    sub_rows = connection.execute("SELECT id FROM sub_components WHERE activity_id = ?", (activity_id,)).fetchall()
    for sub_row in sub_rows:
        apply_rules_for_sub_component(connection, sub_row["id"])
    return get_activity_state(connection, activity_id)


def delete_activity(connection: sqlite3.Connection, activity_id: str) -> None:
    connection.execute("DELETE FROM activities WHERE id = ?", (activity_id,))


def _resequence_sub_components(connection: sqlite3.Connection, activity_id: str) -> None:
    rows = connection.execute(
        "SELECT id FROM sub_components WHERE activity_id = ? ORDER BY sequence, created_at",
        (activity_id,),
    ).fetchall()
    for index, row in enumerate(rows, start=1):
        connection.execute(
            "UPDATE sub_components SET sequence = ?, code = ?, updated_at = ? WHERE id = ?",
            (index, _excel_style_code(index), _now(), row["id"]),
        )


def create_sub_component(connection: sqlite3.Connection, activity_id: str, payload: SubComponentPayload) -> dict[str, Any]:
    next_sequence = connection.execute(
        "SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence FROM sub_components WHERE activity_id = ?",
        (activity_id,),
    ).fetchone()["next_sequence"]
    sub_component_id = _new_id("sub")
    connection.execute(
        """
        INSERT INTO sub_components (id, activity_id, code, name, sequence, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            sub_component_id,
            activity_id,
            _excel_style_code(next_sequence),
            payload.name,
            next_sequence,
            payload.notes or "",
            _now(),
            _now(),
        ),
    )
    return get_activity_state(connection, activity_id)


def update_sub_component(connection: sqlite3.Connection, sub_component_id: str, payload: SubComponentPayload) -> dict[str, Any]:
    activity_row = connection.execute("SELECT activity_id FROM sub_components WHERE id = ?", (sub_component_id,)).fetchone()
    connection.execute(
        """
        UPDATE sub_components
        SET name = ?, notes = ?, updated_at = ?
        WHERE id = ?
        """,
        (payload.name, payload.notes or "", _now(), sub_component_id),
    )
    return get_activity_state(connection, activity_row["activity_id"])


def delete_sub_component(connection: sqlite3.Connection, sub_component_id: str) -> dict[str, Any]:
    activity_row = connection.execute("SELECT activity_id FROM sub_components WHERE id = ?", (sub_component_id,)).fetchone()
    activity_id = activity_row["activity_id"]
    connection.execute("DELETE FROM sub_components WHERE id = ?", (sub_component_id,))
    _resequence_sub_components(connection, activity_id)
    return get_activity_state(connection, activity_id)


def create_form_selection(connection: sqlite3.Connection, sub_component_id: str, payload: FormSelectionPayload) -> dict[str, Any]:
    selection_id = _new_id("form")
    connection.execute(
        """
        INSERT INTO activity_form_selections (id, sub_component_id, form_code, attributes_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (selection_id, sub_component_id, payload.form_code, json.dumps(payload.attributes, ensure_ascii=True), _now(), _now()),
    )
    apply_rules_for_sub_component(connection, sub_component_id)
    activity_id = connection.execute("SELECT activity_id FROM sub_components WHERE id = ?", (sub_component_id,)).fetchone()["activity_id"]
    return get_activity_state(connection, activity_id)


def update_form_selection(connection: sqlite3.Connection, selection_id: str, payload: FormSelectionPayload) -> dict[str, Any]:
    sub_component_row = connection.execute(
        "SELECT sub_component_id FROM activity_form_selections WHERE id = ?",
        (selection_id,),
    ).fetchone()
    sub_component_id = sub_component_row["sub_component_id"]
    connection.execute(
        """
        UPDATE activity_form_selections
        SET form_code = ?, attributes_json = ?, updated_at = ?
        WHERE id = ?
        """,
        (payload.form_code, json.dumps(payload.attributes, ensure_ascii=True), _now(), selection_id),
    )
    apply_rules_for_sub_component(connection, sub_component_id)
    activity_id = connection.execute("SELECT activity_id FROM sub_components WHERE id = ?", (sub_component_id,)).fetchone()["activity_id"]
    return get_activity_state(connection, activity_id)


def delete_form_selection(connection: sqlite3.Connection, selection_id: str) -> dict[str, Any]:
    sub_component_row = connection.execute(
        """
        SELECT activity_form_selections.sub_component_id, sub_components.activity_id
        FROM activity_form_selections
        JOIN sub_components ON sub_components.id = activity_form_selections.sub_component_id
        WHERE activity_form_selections.id = ?
        """,
        (selection_id,),
    ).fetchone()
    connection.execute("DELETE FROM activity_form_selections WHERE id = ?", (selection_id,))
    apply_rules_for_sub_component(connection, sub_component_row["sub_component_id"])
    return get_activity_state(connection, sub_component_row["activity_id"])


def toggle_account_selection(connection: sqlite3.Connection, selection_id: str, is_selected: bool) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT budget_account_selections.sub_component_id, sub_components.activity_id
        FROM budget_account_selections
        JOIN sub_components ON sub_components.id = budget_account_selections.sub_component_id
        WHERE budget_account_selections.id = ?
        """,
        (selection_id,),
    ).fetchone()
    connection.execute(
        """
        UPDATE budget_account_selections
        SET is_selected = ?, updated_at = ?
        WHERE id = ?
        """,
        (1 if is_selected else 0, _now(), selection_id),
    )
    if is_selected:
        _ensure_default_lines(connection, selection_id)
    return get_activity_state(connection, row["activity_id"])


def add_manual_account(connection: sqlite3.Connection, sub_component_id: str, payload: ManualAccountPayload) -> dict[str, Any]:
    existing = connection.execute(
        """
        SELECT id FROM budget_account_selections
        WHERE sub_component_id = ? AND account_code = ? AND is_manual = 1
        """,
        (sub_component_id, payload.account_code),
    ).fetchone()
    if existing is None:
        selection_id = _new_id("account")
        connection.execute(
            """
            INSERT INTO budget_account_selections (
                id, sub_component_id, form_selection_id, account_code, recommendation_reason, source_rule_id,
                is_recommended, is_selected, is_manual, created_at, updated_at
            )
            VALUES (?, ?, NULL, ?, ?, NULL, 0, 1, 1, ?, ?)
            """,
            (selection_id, sub_component_id, payload.account_code, payload.recommendation_reason or "", _now(), _now()),
        )
        _ensure_default_lines(connection, selection_id)
    activity_id = connection.execute("SELECT activity_id FROM sub_components WHERE id = ?", (sub_component_id,)).fetchone()["activity_id"]
    return get_activity_state(connection, activity_id)


def create_budget_line(connection: sqlite3.Connection, account_selection_id: str, payload: BudgetLinePayload) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT budget_account_selections.sub_component_id, sub_components.activity_id
        FROM budget_account_selections
        JOIN sub_components ON sub_components.id = budget_account_selections.sub_component_id
        WHERE budget_account_selections.id = ?
        """,
        (account_selection_id,),
    ).fetchone()
    next_sort = connection.execute(
        "SELECT COALESCE(MAX(sort_order), 0) + 10 AS next_sort FROM budget_lines WHERE account_selection_id = ?",
        (account_selection_id,),
    ).fetchone()["next_sort"]
    amount = payload.volume * payload.unit_price
    connection.execute(
        """
        INSERT INTO budget_lines (
            id, account_selection_id, template_id, item_name, specification, volume, unit,
            unit_price, suggested_unit_price, amount, suggestion_note, pricing_context_json,
            is_manual, sort_order, created_at, updated_at
        )
        VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, '{}', 1, ?, ?, ?)
        """,
        (
            _new_id("line"),
            account_selection_id,
            payload.item_name,
            payload.specification or "",
            payload.volume,
            payload.unit,
            payload.unit_price,
            payload.unit_price,
            amount,
            "Baris manual ditambahkan pengguna.",
            next_sort,
            _now(),
            _now(),
        ),
    )
    return get_activity_state(connection, row["activity_id"])


def update_budget_line(connection: sqlite3.Connection, line_id: str, payload: BudgetLineUpdatePayload) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT budget_lines.*, sub_components.activity_id
        FROM budget_lines
        JOIN budget_account_selections ON budget_account_selections.id = budget_lines.account_selection_id
        JOIN sub_components ON sub_components.id = budget_account_selections.sub_component_id
        WHERE budget_lines.id = ?
        """,
        (line_id,),
    ).fetchone()
    current = _row_to_dict(row)
    item_name = payload.item_name if payload.item_name is not None else current["item_name"]
    specification = payload.specification if payload.specification is not None else current["specification"]
    volume = payload.volume if payload.volume is not None else current["volume"]
    unit = payload.unit if payload.unit is not None else current["unit"]
    unit_price = payload.unit_price if payload.unit_price is not None else current["unit_price"]
    amount = _to_float(volume) * _to_float(unit_price)
    connection.execute(
        """
        UPDATE budget_lines
        SET item_name = ?, specification = ?, volume = ?, unit = ?, unit_price = ?, amount = ?, updated_at = ?
        WHERE id = ?
        """,
        (item_name, specification or "", volume, unit, unit_price, amount, _now(), line_id),
    )
    return get_activity_state(connection, row["activity_id"])


def delete_budget_line(connection: sqlite3.Connection, line_id: str) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT sub_components.activity_id
        FROM budget_lines
        JOIN budget_account_selections ON budget_account_selections.id = budget_lines.account_selection_id
        JOIN sub_components ON sub_components.id = budget_account_selections.sub_component_id
        WHERE budget_lines.id = ?
        """,
        (line_id,),
    ).fetchone()
    connection.execute("DELETE FROM budget_lines WHERE id = ?", (line_id,))
    return get_activity_state(connection, row["activity_id"])


def activity_summary(connection: sqlite3.Connection, activity_id: str) -> dict[str, Any]:
    activity = connection.execute("SELECT * FROM activities WHERE id = ?", (activity_id,)).fetchone()
    if activity is None:
        return {}

    selected_lines = connection.execute(
        """
        SELECT
            sub_components.id AS sub_component_id,
            sub_components.code AS sub_component_code,
            sub_components.name AS sub_component_name,
            budget_account_selections.account_code,
            budget_accounts.name AS account_name,
            budget_lines.amount
        FROM budget_lines
        JOIN budget_account_selections ON budget_account_selections.id = budget_lines.account_selection_id
        JOIN budget_accounts ON budget_accounts.code = budget_account_selections.account_code
        JOIN sub_components ON sub_components.id = budget_account_selections.sub_component_id
        WHERE sub_components.activity_id = ?
          AND budget_account_selections.is_selected = 1
        """,
        (activity_id,),
    ).fetchall()

    total = 0.0
    per_account: dict[str, dict[str, Any]] = {}
    per_sub_component: dict[str, dict[str, Any]] = {}
    for row in selected_lines:
        amount = _to_float(row["amount"])
        total += amount
        account_key = row["account_code"]
        sub_key = row["sub_component_id"]
        if account_key not in per_account:
            per_account[account_key] = {
                "account_code": account_key,
                "account_name": row["account_name"],
                "total": 0.0,
            }
        if sub_key not in per_sub_component:
            per_sub_component[sub_key] = {
                "sub_component_id": sub_key,
                "code": row["sub_component_code"],
                "name": row["sub_component_name"],
                "total": 0.0,
            }
        per_account[account_key]["total"] += amount
        per_sub_component[sub_key]["total"] += amount

    remaining = _to_float(activity["budget_ceiling"]) - total
    warnings: list[str] = []
    if remaining < 0:
        warnings.append("Total RAB melebihi pagu anggaran kegiatan.")
    if not per_sub_component:
        warnings.append("Belum ada akun aktif yang menghasilkan total anggaran.")

    sub_components_without_forms = connection.execute(
        """
        SELECT sub_components.code, sub_components.name
        FROM sub_components
        LEFT JOIN activity_form_selections ON activity_form_selections.sub_component_id = sub_components.id
        WHERE sub_components.activity_id = ?
        GROUP BY sub_components.id
        HAVING COUNT(activity_form_selections.id) = 0
        ORDER BY sub_components.sequence
        """,
        (activity_id,),
    ).fetchall()
    for row in sub_components_without_forms:
        warnings.append(f"Sub komponen {row['code']}. {row['name']} belum memiliki bentuk kegiatan.")

    selected_accounts_without_lines = connection.execute(
        """
        SELECT sub_components.code, budget_account_selections.account_code
        FROM budget_account_selections
        JOIN sub_components ON sub_components.id = budget_account_selections.sub_component_id
        LEFT JOIN budget_lines ON budget_lines.account_selection_id = budget_account_selections.id
        WHERE sub_components.activity_id = ?
          AND budget_account_selections.is_selected = 1
        GROUP BY budget_account_selections.id
        HAVING COUNT(budget_lines.id) = 0
        ORDER BY sub_components.sequence, budget_account_selections.account_code
        """,
        (activity_id,),
    ).fetchall()
    for row in selected_accounts_without_lines:
        warnings.append(f"Akun aktif {row['account_code']} pada sub komponen {row['code']} belum memiliki detail belanja.")

    zero_lines = connection.execute(
        """
        SELECT COUNT(*) AS count
        FROM budget_lines
        JOIN budget_account_selections ON budget_account_selections.id = budget_lines.account_selection_id
        JOIN sub_components ON sub_components.id = budget_account_selections.sub_component_id
        WHERE sub_components.activity_id = ?
          AND budget_account_selections.is_selected = 1
          AND budget_lines.unit_price = 0
        """,
        (activity_id,),
    ).fetchone()["count"]
    if zero_lines:
        warnings.append(f"Ada {zero_lines} detail belanja aktif yang masih bernilai Rp0 dan perlu diverifikasi.")

    utilization = 0.0
    if _to_float(activity["budget_ceiling"]) > 0:
        utilization = round((total / _to_float(activity["budget_ceiling"])) * 100, 2)

    return {
        "grand_total": total,
        "budget_ceiling": _to_float(activity["budget_ceiling"]),
        "remaining_budget": remaining,
        "utilization_percent": utilization,
        "warnings": warnings,
        "totals_by_account": sorted(per_account.values(), key=lambda item: item["account_code"]),
        "totals_by_sub_component": sorted(per_sub_component.values(), key=lambda item: item["code"]),
    }


def get_activity_state(connection: sqlite3.Connection, activity_id: str) -> dict[str, Any]:
    activity_row = connection.execute("SELECT * FROM activities WHERE id = ?", (activity_id,)).fetchone()
    activity = _row_to_dict(activity_row)
    if activity is None:
        raise ValueError("Activity not found")

    sub_rows = connection.execute(
        """
        SELECT * FROM sub_components
        WHERE activity_id = ?
        ORDER BY sequence, created_at
        """,
        (activity_id,),
    ).fetchall()
    sub_components = [_row_to_dict(row) for row in sub_rows]

    form_rows = connection.execute(
        """
        SELECT activity_form_selections.*, activity_forms.name AS form_name, activity_forms.description AS form_description
        FROM activity_form_selections
        JOIN activity_forms ON activity_forms.code = activity_form_selections.form_code
        JOIN sub_components ON sub_components.id = activity_form_selections.sub_component_id
        WHERE sub_components.activity_id = ?
        ORDER BY activity_form_selections.created_at, activity_form_selections.id
        """,
        (activity_id,),
    ).fetchall()
    forms_by_sub_component: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in form_rows:
        payload = _row_to_dict(row)
        payload["attributes"] = _json_loads(row["attributes_json"], {})
        forms_by_sub_component[row["sub_component_id"]].append(payload)

    account_rows = connection.execute(
        """
        SELECT
            budget_account_selections.*,
            budget_accounts.name AS account_name,
            budget_accounts.category AS account_category
        FROM budget_account_selections
        JOIN budget_accounts ON budget_accounts.code = budget_account_selections.account_code
        JOIN sub_components ON sub_components.id = budget_account_selections.sub_component_id
        WHERE sub_components.activity_id = ?
        ORDER BY sub_components.sequence, budget_account_selections.account_code, budget_account_selections.created_at
        """,
        (activity_id,),
    ).fetchall()
    lines_rows = connection.execute(
        """
        SELECT budget_lines.*
        FROM budget_lines
        JOIN budget_account_selections ON budget_account_selections.id = budget_lines.account_selection_id
        JOIN sub_components ON sub_components.id = budget_account_selections.sub_component_id
        WHERE sub_components.activity_id = ?
        ORDER BY budget_lines.sort_order, budget_lines.created_at
        """,
        (activity_id,),
    ).fetchall()
    lines_by_selection: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in lines_rows:
        line = _row_to_dict(row)
        line["pricing_context"] = _json_loads(row["pricing_context_json"], {})
        lines_by_selection[row["account_selection_id"]].append(line)

    accounts_by_sub_component: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in account_rows:
        account = _row_to_dict(row)
        lines = lines_by_selection.get(row["id"], [])
        account_total = sum(_to_float(line["amount"]) for line in lines)
        account["lines"] = lines
        account["account_total"] = account_total
        accounts_by_sub_component[row["sub_component_id"]].append(account)

    summary = activity_summary(connection, activity_id)
    reference_data = list_reference_data(connection)

    for sub_component in sub_components:
        sub_component["forms"] = forms_by_sub_component.get(sub_component["id"], [])
        sub_component["accounts"] = accounts_by_sub_component.get(sub_component["id"], [])
        sub_component["sub_total"] = sum(
            _to_float(account["account_total"])
            for account in sub_component["accounts"]
            if account["is_selected"]
        )

    return {
        "activity": activity,
        "sub_components": sub_components,
        "summary": summary,
        "reference": reference_data,
    }
