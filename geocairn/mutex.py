"""Marque de présence du programme, lue par l'installeur Windows.

Une mise à jour remplace les fichiers du dossier d'installation. Si Géo Cairn
tourne encore, Windows les retient : l'installation s'arrête à mi-chemin et
laisse un programme mêlant deux versions — panne difficile à comprendre pour
l'utilisateur, et impossible à reproduire chez soi. L'installeur interroge donc
cette marque avant de commencer, et invite à fermer la fenêtre.

Le nom est repris tel quel dans installateur.iss (directive `AppMutex`) : les
deux doivent rester identiques, ce que vérifient les tests.
"""

from __future__ import annotations

import os

#: Nom du mutex Windows. Sans préfixe « Global\\ » : l'installation se fait dans
#: le profil de l'utilisateur, la session courante suffit donc.
MUTEX_NAME = "GeoCairn.Application.Running"

#: Conservé pour toute la vie du processus : Windows libère le mutex à la
#: fermeture du programme, y compris s'il est tué.
_handle = None


def claim() -> bool:
    """Pose la marque de présence. Vrai si elle est bien en place.

    Ne rien poser n'empêche pas le programme de fonctionner : au pire,
    l'installeur ne saura pas que Géo Cairn tourne. L'échec est donc silencieux.
    """
    global _handle
    if _handle is not None:
        return True
    if os.name != "nt":
        return False

    import ctypes

    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        # Sans restype explicite, ctypes ramène le descripteur dans un entier
        # 32 bits et le tronque : en 64 bits, la valeur devient inutilisable.
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CreateMutexW.argtypes = [
            ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p
        ]
        handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    except (AttributeError, OSError, ValueError):
        return False

    if not handle:
        return False
    _handle = handle
    return True
