# Historique des opérations

La page **Historique**, dans la barre latérale et les raccourcis de l’accueil,
présente les opérations lancées depuis MintTweaks pour le compte courant.
L’enregistrement commence avec cette fonctionnalité ; les anciens journaux ne
sont pas importés et les actions réalisées dans d’autres applications ne sont
pas recensées.

## Consulter les opérations

Les entrées apparaissent de la plus récente à la plus ancienne, par pages de
50. Utiliser **Opérations plus anciennes**, **Opérations plus récentes** et le
filtre de résultat. Déplier une entrée pour consulter le module, les dates de
début et de fin et les références de sauvegarde disponibles. Les dates sont
affichées dans le fuseau local.

| Résultat | Signification |
| --- | --- |
| En cours | L’opération a commencé dans cette session. |
| Terminé | La fonction a terminé sans exception ni résultat signalant un échec. Cela ne prouve pas le fonctionnement réel du logiciel ou du service. |
| Échec | Une exception ou un résultat d’échec a été reçu. Des changements peuvent avoir eu lieu avant l’erreur. |
| Simulation | L’opération a terminé dans l’instance de simulation, sans action système réelle. |
| Résultat inconnu après interruption | Une ancienne session n’a pas enregistré la fin. Vérifier l’état réel avant de relancer l’action. |
| Erreur d’interface après l’opération | Le traitement du résultat par l’interface a échoué. L’action système peut avoir abouti. |

Les opérations sont enregistrées au niveau de la réservation commune utilisée
par les pages. Les analyses ordinaires exécutées en arrière-plan ne sont pas
ajoutées. Certaines consultations administratives Samba qui utilisent cette
réservation apparaissent également. Une confirmation annulée ou une opération
refusée parce qu’une autre est active ne crée pas d’entrée.

## Sauvegardes et restauration

Les opérations associent les chemins des sauvegardes qu’elles créent pour :

- les configurations Samba ;
- les profils d’apparence et les thèmes Cinnamon remplacés ;
- les configurations du terminal et le précédent shell de connexion ;
- les activations Stow et les journaux utilisés pour les annuler.

Les références sont enregistrées dès que ces sauvegardes sont créées, y compris
si l’action échoue ensuite. Leur présence ne garantit pas que le fichier existe
encore ou qu’une récupération a réussi. L’absence de référence ne signifie pas
qu’aucune sauvegarde n’existe : certaines sauvegardes, notamment celles des
auxiliaires administrateur, ne sont pas exposées à l’historique.

**Ouvrir le module d’origine** ramène à ses commandes habituelles. La page
Historique ne restaure pas directement un fichier et ne relance pas une commande.
Utiliser l’aperçu et la restauration proposés par le module concerné lorsqu’ils
existent. Les outils externes restent responsables des opérations qui ne sont
pas réversibles par MintTweaks.

## Conservation et confidentialité

Les métadonnées sont conservées dans
`~/.local/share/minttweaks/history/operations.sqlite3`, ou sous `XDG_DATA_HOME`
si défini. Le dossier est privé (`0700`) et le fichier utilise `0600`.
L’historique de simulation se trouve dans le sous-dossier `simulation` et reste
séparé de l’historique réel.

L’historique contient le nom de l’action, son module, ses dates, son résultat et
les chemins de sauvegarde associés. Il ne copie ni les mots de passe, ni les
sorties des commandes, ni les messages d’exception, ni le contenu des sauvegardes.
Les chemins peuvent néanmoins contenir des informations personnelles. Les
journaux techniques existants restent distincts et suivent leurs propres règles.

Les entrées sont conservées entre les lancements, sans purge automatique. La
consultation est en lecture seule. Un fichier corrompu ou d’une version inconnue
n’est pas remplacé ; la page affiche une erreur. Si l’écriture échoue, une alerte
signale que l’historique est incomplet, sans bloquer l’opération demandée.

## Validation

Les tests utilisent SQLite, des fichiers temporaires, des exécuteurs simulés et
le double GTK. Ils couvrent la persistance, les filtres, la pagination, les
écritures concurrentes, les interruptions, les échecs et la préservation des
fichiers non reconnus. Le rendu, la navigation et les opérations réelles de cette
nouvelle page restent à vérifier dans une session Linux Mint.
