# Rapport de stage — mode d'emploi

`rapport.tex` compile tel quel sur Overleaf avec les réglages par défaut
(pdfLaTeX). Aucun paquet hors distribution standard n'est utilisé.

---

## 1. À remplir avant de compiler

Les champs entre crochets sur la page de garde et dans la section 1.1 :

| Emplacement | Champ |
|---|---|
| Page de garde | Nom de l'université, nom de l'école ou institut |
| Page de garde | Logo de l'université (cadre réservé) |
| Page de garde | Classe, encadrant académique, encadrant professionnel |
| Page de garde | Nom de l'organisme d'accueil |
| Chapitre 1, section I | Présentation de l'entreprise (paragraphe entier à rédiger) |

---

## 2. Les 24 figures

Deux types de cadres réservés apparaissent dans le PDF.

**Captures d'écran (11).** Cadre gris avec la légende. Remplacez le bloc
`\captureph{...}{...}{...}` par un `\includegraphics` classique :

```latex
\begin{figure}[htbp]
  \centering
  \includegraphics[width=0.86\textwidth]{figures/ma-capture.png}
  \caption{Légende identique}
  \label{fig:monlabel}
\end{figure}
```

Captures à produire depuis l'application : assistant de connexion, liste des
projets, liste des exécutions, page de défaillance, panneau d'analyse,
recommandation avec différence, page de remédiation, dialogue d'approbation, vue
des anomalies, tableau de bord projet, palette de commandes.

**Schémas (13).** Le cadre affiche directement l'invite de génération dans le
PDF. Copiez ce texte dans l'outil de votre choix, générez l'image, puis
remplacez le bloc de la même manière. Les invites sont rédigées pour produire un
rendu homogène : style plat, palette vert foncé et gris, fond blanc.

Schémas à produire : organigramme, cycle itératif, architecture générale,
séquence d'ingestion, cas d'utilisation, modèle de données, chaîne de
récupération augmentée, chaîne d'analyse, arbre de décision des politiques.

---

## 3. Volume

Environ 13 800 mots, 24 figures, 11 tableaux, 2 extraits de code, 5 chapitres.

Le rendu se situe autour de 40 à 45 pages avec les cadres réservés. Les cadres
sont plus hauts que ne le seront la plupart des images finales, donc le volume
se rapprochera de 38 à 42 pages une fois les figures insérées. Si vous devez
descendre sous 40, les sections les plus faciles à condenser sans perte sont le
tableau du backlog (2.III.1) et la liste des besoins fonctionnels (2.I.2).

---

## 4. Un écart assumé par rapport au plan initial

Le plan fourni prévoyait une section « Architecture événementielle Kafka ».

**PipeMind n'utilise pas Kafka.** L'architecture asynchrone repose sur des
webhooks HTTP signés, des files Redis pilotées par Laravel Horizon, et une
diffusion WebSocket via Laravel Reverb. La section 2.II.2 décrit ce mécanisme
réel sous le titre « Architecture événementielle asynchrone ».

Le rapport étant soutenu à l'oral, une mention de Kafka aurait été la
affirmation la plus risquée du document : une seule question sur le nombre de
partitions ou sur la stratégie de consommation aurait suffi à la mettre en
défaut. Si vous préférez néanmoins conserver le titre d'origine, il faut alors
mettre Kafka en œuvre, et non seulement le citer.

---

## 5. Traçabilité des chiffres

Chaque valeur citée provient du dépôt et peut être retrouvée :

| Chiffre | Source |
|---|---|
| Seuil 0,75 → 0,55 | `experiments/similarity-threshold.md` |
| Seuil 0,60 → 0,40, fragments 400 → 150 | `experiments/knowledge-retrieval.md` |
| 22 anomalies sur 24 → 3 | `experiments/anomaly-v1.md` |
| Latence 4,14 s, coût 0,0015 $ | `experiments/prompt-v1.md` |
| Coût 0,00087 $, cache 6 %, regroupement 3,22 | `reports/evaluation-final.md` |
| 624 tests, 31 tables, 87 points d'entrée | mesurés sur les dépôts |

Le chapitre 5 et la conclusion énoncent explicitement ce qui n'a pas pu être
mesuré. Cette partie mérite d'être conservée : un rapport qui annonce de bons
résultats partout se défend moins bien qu'un rapport qui délimite ce qu'il a
prouvé.
