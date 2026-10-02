"""
Shield Technology Synthetic Demo Data Seeder.
Generates 10 realistic, anonymized commercial equipment sheets & SLA service packages.
Enables instant local execution and automated testing without external dependencies.
"""

import sys
import os

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from typing import List, Optional
from domain.entities import EquipmentEntity
from domain.enums import EquipmentCategory
from services.search_service import SearchService, search_service


DEMO_EQUIPMENT_DATA: List[EquipmentEntity] = [
    EquipmentEntity(
        id="eq_panasonic_4k_ai",
        slug="panasonic-ipro-4k-ai-bullet",
        name="Caméra Panasonic i-PRO 4K IA Bullet",
        category=EquipmentCategory.CAMERA_4K_IA,
        manufacturer="Panasonic i-PRO",
        description="Caméra de vidéosurveillance Ultra HD 4K avec processeur d'intelligence artificielle embarqué (Edge AI) pour la classification d'humains et véhicules.",
        technical_specs={
            "resolution": "3840x2160 (8.4MP)",
            "framerate": "30 fps @ 4K",
            "sensor": "1/1.8 CMOS",
            "wdr": "120 dB",
            "ir_distance": "50 mètres",
            "compression": "H.265 / H.264 / Smart Coding",
            "protection": "IP66, IP67, IK10",
            "power": "PoE (IEEE802.3af) / 12V DC",
        },
        certifications=["NDAA", "CE", "UL", "ISO 9001"],
        warranty_months=60,
        price_tnd=890.0,
        in_stock=True,
    ),
    EquipmentEntity(
        id="eq_grundig_4mp_bullet",
        slug="grundig-pro-4mp-ir-bullet",
        name="Caméra Grundig Pro 4MP Infrarouge",
        category=EquipmentCategory.CAMERA_4K_IA,
        manufacturer="Grundig Security Germany",
        description="Caméra extérieure anti-vandale 4 Mégapixels haute fidélité pour sites industriels, entrepôts et zones périphériques.",
        technical_specs={
            "resolution": "2560x1440 (4MP)",
            "lens": "Motorisé 2.8-12mm autofocus",
            "ir_distance": "40 mètres",
            "wdr": "True WDR 120dB",
            "protection": "IP67 étanche, IK10 anti-vandale",
        },
        certifications=["CE", "RoHS", "DIN VDE 0830"],
        warranty_months=36,
        price_tnd=480.0,
        in_stock=True,
    ),
    EquipmentEntity(
        id="eq_dsc_neo_kit",
        slug="dsc-powerseries-neo-kit-pro",
        name="Kit Alarme DSC PowerSeries Neo Hybride",
        category=EquipmentCategory.ALARM_GRADE_3,
        manufacturer="DSC / Johnson Controls",
        description="Centrale anti-intrusion professionnelle certifiée Grade 2/3 dotée de la technologie radio militaire bidirectionnelle PowerG 2km portée.",
        technical_specs={
            "zones": "Jusqu'à 64 zones filaires et radio",
            "partitions": "8 partitions indépendantes",
            "encryption": "AES-128 militaire",
            "communication": "Double voie IP / LTE 4G",
            "battery_backup": "Batterie 12V 7Ah (autonomie 48h)",
        },
        certifications=["EN 50131 Grade 3", "NF&A2P", "INCERT"],
        warranty_months=36,
        price_tnd=890.0,
        in_stock=True,
    ),
    EquipmentEntity(
        id="eq_satel_integra_128",
        slug="satel-integra-128-wrl",
        name="Centrale Satel Integra 128 Plus",
        category=EquipmentCategory.ALARM_GRADE_3,
        manufacturer="Satel",
        description="Système d'alarme de haute sécurité pour banques, bijouteries et sites sensibles OIV avec domotique avancée.",
        technical_specs={
            "zones": "128 zones programmables",
            "outputs": "128 sorties de télécommande",
            "bus": "Double bus de communication sécurisé",
            "grade": "Grade 3 certifié",
        },
        certifications=["EN 50131 Grade 3", "CE"],
        warranty_months=24,
        price_tnd=1250.0,
        in_stock=True,
    ),
    EquipmentEntity(
        id="eq_fireclass_fc501",
        slug="fireclass-fc501-addressable-panel",
        name="Centrale Détection Incendie FireClass FC501",
        category=EquipmentCategory.FIRE_EN54,
        manufacturer="FireClass / Johnson Controls",
        description="Centrale adressable 1 boucle gérant jusqu'à 128 adresses avec localisation précise au mètre près du foyer d'incendie.",
        technical_specs={
            "loop_capacity": "1 boucle / 128 points adressables",
            "sounder_outputs": "2 lignes de sirènes supervisées",
            "relays": "Relais alarme et dérangement libres de potentiel",
            "display": "Écran LCD rétroéclairé 4x40 caractères",
        },
        certifications=["EN54-2", "EN54-4", "CE DPC"],
        warranty_months=36,
        price_tnd=1450.0,
        in_stock=True,
    ),
    EquipmentEntity(
        id="eq_fireclass_fc400p",
        slug="fireclass-fc400-optical-smoke",
        name="Détecteur Optique de Fumée FireClass FC400P",
        category=EquipmentCategory.FIRE_EN54,
        manufacturer="FireClass",
        description="Détecteur optique adressable haute sensibilité avec algorithme de compensation dynamique des poussières pour éliminer les fausses alertes.",
        technical_specs={
            "detection": "Chambre optique laser",
            "operating_voltage": "20 à 30V DC",
            "current": "0.15 mA repos / 3 mA alarme",
            "coverage": "Jusqu'à 100 m² par détecteur",
        },
        certifications=["EN54-7", "VdS", "LPCB"],
        warranty_months=36,
        price_tnd=115.0,
        in_stock=True,
    ),
    EquipmentEntity(
        id="eq_kantech_kt4",
        slug="kantech-kt4-access-controller",
        name="Contrôleur d'Accès Kantech KT-4 Four-Door",
        category=EquipmentCategory.ACCESS_BIOMETRIC,
        manufacturer="Kantech / Johnson Controls",
        description="Contrôleur réseau Ethernet 4 portes gérant jusqu'à 100 000 utilisateurs avec mémoire tampon locale de 20 000 événements hors-ligne.",
        technical_specs={
            "doors": "4 lecteurs Wiegand ou OSDP v2",
            "inputs": "16 entrées supervisées intégrées",
            "outputs": "4 relais de gâche C/NO/NC",
            "users": "100 000 badges / empreintes",
            "anti_passback": "Anti-passback strict mondial",
        },
        certifications=["UL 294", "CE", "FCC Class A"],
        warranty_months=60,
        price_tnd=1890.0,
        in_stock=True,
    ),
    EquipmentEntity(
        id="eq_turnstile_tripod",
        slug="turnstile-tripod-inox-304",
        name="Tourniquet Tripode Inox 304 Brossé",
        category=EquipmentCategory.ACCESS_BIOMETRIC,
        manufacturer="Shield Access Engineering",
        description="Obstacle physique électromécanique bidirectionnel pour le filtrage sécurisé des flux piétons à l'entrée d'usines et d'immeubles tertiaires.",
        technical_specs={
            "material": "Acier Inoxydable AISI 304 épaisseur 1.5mm",
            "throughput": "35 personnes par minute",
            "drop_arm": "Bras tombant automatique en cas d'alerte incendie",
            "integration": "Compatible lecteurs RFID, biométrie faciale et QR Code",
        },
        certifications=["CE", "ISO 9001"],
        warranty_months=24,
        price_tnd=2850.0,
        in_stock=True,
    ),
    EquipmentEntity(
        id="eq_dell_t340_server",
        slug="dell-poweredge-t340-security",
        name="Serveur Dédié NVR/Sécurité Dell PowerEdge T340",
        category=EquipmentCategory.IT_NETWORKING,
        manufacturer="Dell Technologies",
        description="Serveur tour haute fiabilité avec disques de qualité surveillance configurés en RAID 1 matériel et carte de management à distance iDRAC9.",
        technical_specs={
            "processor": "Intel Xeon E-2224 3.4GHz 4C/4T",
            "ram": "16GB DDR4 ECC UDIMM 2666MT/s",
            "storage": "2x 4TB Enterprise SATA RAID-1 Matériel",
            "power": "Double alimentation redondante 495W Hot-Plug",
            "network": "2x 1GbE LOM ports intégrés",
        },
        certifications=["ENERGY STAR", "CE", "FCC"],
        warranty_months=36,
        price_tnd=3200.0,
        in_stock=True,
    ),
    EquipmentEntity(
        id="eq_sla_critical_247",
        slug="contrat-sla-mission-critique-247",
        name="Contrat de Maintenance SLA Mission Critique 24/7/365",
        category=EquipmentCategory.SLA_SERVICE,
        manufacturer="Shield Technology Service Lab",
        description="Prestation de maintenance globale préventive et curative avec astreinte permanente, intervention garantie sous 2 heures et pièces de rechange sur site.",
        technical_specs={
            "intervention_guarantee": "2 heures sur site (Tunis, Sousse, Sfax)",
            "remote_support": "Hotline technique ingénieur 24/7/365",
            "preventive_audits": "4 audits approfondis par an avec rapport certifié",
            "replacement_hardware": "Prêt immédiat de matériel tampon de secours",
            "otdr_testing": "Mesures réflectométrie fibre optique et certification cuivre",
        },
        certifications=["ISO 9001 Service Quality", "Agrément Johnson Controls"],
        warranty_months=12,
        price_tnd=550.0,
        in_stock=True,
    ),
]


def seed_catalog_data(target_service: Optional[SearchService] = None) -> int:
    """Populates vector store with synthetic enterprise security equipment."""
    svc = target_service or search_service
    count = svc.index_batch(DEMO_EQUIPMENT_DATA)
    print(f"[OK] Successfully seeded {count} security items into Vector Store.")
    return count


if __name__ == "__main__":
    print("[INIT] Initializing Shield Technology Demo Data Seeder...")
    total = seed_catalog_data()
    print(f"[READY] Total indexed items in vector catalog: {total}")
