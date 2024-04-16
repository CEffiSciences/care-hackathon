import osimport numpy as npimport pandas as pdimport matplotlib.pyplot as pltfrom matplotlib.colors import ListedColormapimport plotly.graph_objects as goimport requestsimport nltkfrom nltk.corpus import stopwordsimport sslimport pathlibimport pydanticimport jsonfrom sklearn.cluster import KMeansfrom sklearn.feature_extraction.text import TfidfVectorizerfrom sklearn.decomposition import TruncatedSVDfrom sklearn.manifold import TSNEfrom sentence_transformers import SentenceTransformerfrom langdetect import detect, DetectorFactory, lang_detect_exceptionfrom langdetect.lang_detect_exception import LangDetectExceptionfrom openai import OpenAIimport hdbscan# Clés APIapi_key = os.getenv('SEMANTIC_SCHOLAR_API_KEY')#openai.api_key = os.getenv('OPENAI_API_KEY')#deepl_api_key = os.getenv('DEEPL_API_KEY')client = OpenAI()try:    # Crée un contexte SSL qui ne vérifie pas les certificats.    _create_unverified_https_context = ssl._create_unverified_contextexcept AttributeError:    # Legacy Python qui n'a pas ssl._create_unverified_context.    passelse:    # Remplace la création du contexte par défaut par la création non vérifiée.    ssl._create_default_https_context = _create_unverified_https_context# Assurez-vous que les données NLTK nécessaires sont téléchargées# nltk.download('stopwords')nltk.download('punkt')### Étape 1 : Récupération des données via l'API ###def semantic(url, params):    req = requests.get(      url,      headers={ "x-api-key": api_key },      params=params,    )    try:        return req.json()    except KeyError as e:        raise ValueError(req.status_code, req.json()) from eclass Papers(pydantic.BaseModel):    class Paper(pydantic.BaseModel):        paperId: str        title: str        abstract: str        referenceCount: int        citationCount: int        influentialCitationCount: int        fieldsOfStudy: list | None        s2FieldsOfStudy: list        publicationTypes: list[str] | None        class Journal(pydantic.BaseModel):            name: str | None = None            volume: str | None = None        journal: Journal | None    papers: dict[str, Paper]call = Noneresults = []while call is None or call['token']:    call = semantic(    url='https://api.semanticscholar.org/graph/v1/paper/search/bulk',    params=dict(        query="bioterrorism",        fields=','.join(Papers.Paper.model_fields.keys()),    ) | ({'token': call['token']} if call else {})    )    print(call)    results += call['data']# Enlever les articles sans abstractpapers = [result for result in results if result.get('abstract') is not None]### Étape 2 : Prétraitement des textes #### Traduire les titres et les abstractsDetectorFactory.seed = 0def detect_language(text):    """Détecter si le texte est en anglais."""    try:        if len(text.strip()) == 0:            return None        languages = detect_langs(text)        for language in languages:            # Vérifier si la langue détectée est l'anglais avec forte probabilité            if language.lang == 'en' and language.prob > 0.99:                return 'en'        return None    except LangDetectException:        # Retourner un code de langue neutre si la détection échoue        return Nonepaper_languagues = [detect_language(paper["abstract"]) for paper in papers]def translate_to_en(paper):    if detect_language(paper["abstract"]) != 'en':        # Abstract        abstract = paper["abstract"]        prompt = f"Translate or extract an English version of this abstract : '{abstract}'"        response = client.chat.completions.create(            model="gpt-3.5-turbo",            messages=[{"role": "user", "content": prompt}],            temperature=0.0)        paper["abstract"] = response.choices[0].message.content        # Title        title = paper["title"]        prompt = f"Translate this title in English : '{title}'"        response = client.chat.completions.create(            model="gpt-3.5-turbo",            messages=[{"role": "user", "content": prompt}],            temperature=0.0)        paper["title"] = response.choices[0].message.content    return paperpapers_en = [translate_to_en(paper) for paper in papers]papers_en_languagues = [detect_language(paper["abstract"]) for paper in papers_en]### Étape 3 : Clustering des articles #### Générer les embeddings des abstractsmodel = SentenceTransformer('all-mpnet-base-v2')def get_embeddings(texts):    return model.encode(texts, show_progress_bar=True)abstracts = [paper['abstract'] for paper in papers_en]embeddings = get_embeddings(abstracts)# Réduction dimensionnelle avec t-SNE 3Dn_dims = 3tsne = TSNE(n_components=n_dims, random_state=0)embeddings_tSNE = tsne.fit_transform(embeddings)# Clustering avec HBDSCANclusterer = hdbscan.HDBSCAN(min_cluster_size=10, min_samples=7)labels = clusterer.fit_predict(embeddings_tSNE)fig = go.Figure()unique_labels = np.unique(labels)for label in unique_labels:    idx = labels == label    fig.add_trace(go.Scatter3d(        x=embeddings_tSNE[idx, 0], y=embeddings_tSNE[idx, 1], z=embeddings_tSNE[idx, 2],        mode='markers',        marker=dict(            size=5,            line=dict(width=0.5),            opacity=0.8        ),        name=f'Cluster {label}'    ))fig.show()### Étape 4 : Affichage des résultats #### Visualiser les résultats du clusteringclustered_papers = {}for label, paper in zip(labels, papers_en):    if label not in clustered_papers:        clustered_papers[label] = []    clustered_papers[label].append(paper['title'])# Affichage des résultatsfor cluster, titles in clustered_papers.items():    if cluster == -1:        print("Noise:")    else:        print(f"Cluster {cluster}: {len(titles)} articles")    for title in titles[:5]:  # Limiter l'affichage pour lisibilité        print(f" - {title}")    print("...")# Extraction de mots-clés pour chaque clustervectorizer = TfidfVectorizer()X = vectorizer.fit_transform(abstracts)feature_names = vectorizer.get_feature_names_out()top_n = 10global_centroid = X.mean(axis=0) # centroid global du corpus# Calculer les centroids de chaque clustercluster_centroids = {}for cluster in clustered_papers:    if cluster == -1:        continue  # Ignorer le bruit    cluster_indices = [i for i, label in enumerate(labels) if label == cluster]    cluster_matrix = X[cluster_indices]    cluster_centroids[cluster] = cluster_matrix.mean(axis=0)# Identifier les mots les plus représentatifs pour chaque clusterfor cluster, centroid in cluster_centroids.items():    # Différence entre le centroid du cluster et le centroid global    diff = centroid - global_centroid     # Convertir diff en array s'il est sous forme de sparse matrix    if isinstance(diff, np.matrix):        diff = diff.A1   # Obtenir les indices des termes avec les différences les plus grandes    sorted_indices = np.argsort(-diff)  # Négatif pour un ordre décroissant    # Afficher les top 10 mots pour le cluster    top_terms = [feature_names[idx] for idx in sorted_indices[:10]]    print(f"Cluster {cluster} top 10 representative words:")    print(", ".join(top_terms))    print("...")### Étape 5 : Générer des intitulés pour les axes de recherche ###def generate_cluster_label(titles):    # Créer une description en utilisant les titres    description = " ".join(titles)    prompt = f"""        Based on the following titles of research papers, generate a concise and informative title for a research axis that encapsulates the common theme. The title should be succinct, informative, and consist of 3 to 10 words. Do not use a colon (:). Here are some examples of good research axis titles:        - Integrated Syndromic Surveillance for Enhanced Public Health Preparedness        - Innovative Strategies for Rapid Vaccine Development Against Bioterrorism Agents        - Advances Detection, Prevention, and Vaccine Development for Ebola and Other Hemorrhagic Fever Viruses        - Evaluation of Biorisk Threats in Food and Waterborne Pathogens        Given these titles of research papers in the cluster:        {description}        Generate a research axis title:        """    response = client.chat.completions.create(        model="gpt-3.5-turbo",  # Check for the latest available model        messages=[{"role": "user",                    "content": prompt}],        max_tokens=32,        temperature=0.0,        stop=["\n"],        logit_bias={25:-20, 1058:-20})        #top_p=1.0,        #frequency_penalty=0.0,        #presence_penalty=0.0    return response.choices[0].message.contentgenerate_cluster_label(cluster_titles[1])# Aggréger les titres pour chaque clustercluster_titles = {label: [] for label in np.unique(labels) if label != -1}for label, paper in zip(labels, papers_en):    if label != -1:        cluster_titles[label].append(paper['title'])# Générer un label pour chaque clustercluster_labels = {}for cluster, titles in cluster_titles.items():    cluster_labels[cluster] = generate_cluster_label(titles)# Afficher les labels générésfor cluster, label in cluster_labels.items():    print(f"Cluster {cluster}: {label}")# ### Étape 6 : Identifier les axes appliqués (finalement pas utilisé) #### def evaluate_research_type(label):#     prompt = f"""#     Imagine a panel of ten experts in a sub-field of bio-risk management, carefully evaluating their research axis on a scale from 0 to 1, where 0 represents purely fundamental research and 1 represents purely applied research.#     These examples are provided:#     - 'Mathematics of Complexity and Dynamical Systems Theory': 0.07#     - 'Mechanisms of horizontal gene transfers in bacteria': 0.43#     - 'Molecular mechanisms of viral entry into host cells': 0.55#     - 'The role of wildlife in emerging infectious diseases': 0.67#     - 'Epidemiological modeling of infectious diseases': 0.71#     - 'Bioinformatics analysis of epidemic outbreak data': 0.78#     - 'Environmental persistence studies of high-risk pathogens': 0.81#     - 'Public health strategies for pandemic prevention': 0.94#     - 'Development of diagnostic assays for field detection of zoonotic diseases': 0.95#     - 'Surveillance and Control of Hantavirus in the American Southwest': 0.96:#     - 'Implementation of Water Treatment Protocols to Control Cholera': 0.97#     - 'Antibiotic Resistance Management in Hospital Settings in India': 0.97#     - 'Development of Heat-Resistant Tuberculosis Vaccines for Use in Africa' : 0.99#     - 'Vaccine development for Ebola virus adapted for rapid deployment': 0.99#     - 'Rapid Diagnostic Test Development for Malaria Detection in Sub-Saharan Africa' : 1.00#     Based on the following research axis: {label}, each expert provides a score answering the question: "How applied do you consider your research axis?"#     10 expert scores (comma-separated):#     """#     response = client.chat.completions.create(#         model="gpt-3.5-turbo",  # Check for the latest available model#         messages=[{"role": "user", #                    "content": prompt}],#         max_tokens=50,#         temperature=0.0,#         stop=["\n"])#     return response.choices[0].message.content# def parse_scores_and_calculate_median(scores_string):#     # Nettoyer les espaces et séparer les scores par les virgules#     scores = scores_string.strip().split(',')#     # Convertir chaque élément en float#     float_scores = [float(score) for score in scores if score.strip().isdigit() or '.' in score]#     # Calculer la médiane si la liste n'est pas vide#     if float_scores:#         return np.median(float_scores)#     else:#         return None  # Retourner None si aucun score valide n'est extrait# # Évaluer chaque cluster# cluster_application_scores = {}# for cluster, label in cluster_labels.items():#     cluster_application_scores[cluster] = evaluate_research_type(label)# # Faire la médiane des évaluations# parse_scores_and_calculate_median = {}# for cluster, scores in cluster_application_scores.items():#     parse_scores_and_calculate_median[cluster] = parse_scores_and_calculate_average(scores)# # Afficher les scores générées dans l'ordre croissant# parse_scores_and_calculate_median = dict(sorted(parse_scores_and_calculate_median.items(), key=lambda item: item[1]))# for cluster, score in parse_scores_and_calculate_median.items():#     label = cluster_labels[cluster]#     print(f"Cluster {cluster} ({label}): {score}")## Étape 6 : Associer les axes aux problèmes concrets ### ATTENTION : utilise GPT-4 donc plus cher que les autresdef evaluate_leverage_axis_problems(label, threat_type):    prompt = f"""    Imagine a panel of ten experts in the research axis '{label}', each evaluating how directly their research axis contributes to mitigating various problems on a scale from 0 to 1, where 0 indicates no direct contribution and 1 indicates a direct and substantial contribution to reducing the threat.    Each expert provides a score answering the question: "How directly does your research axis '{label}' contribute to reducing {threat_type} bioterrorist threats?"    10 expert scores (comma-separated):    """    response = client.chat.completions.create(        model="gpt-4-turbo",        messages=[{"role": "user",                    "content": prompt}],        max_tokens=60,  # You might need a few more tokens depending on the complexity of the response        temperature=0.0,        stop=["\n"])    return response.choices[0].message.contentdef evaluate_leverage_axis_problems(label):    prompt = f"""    Imagine a panel of ten experts in the research axis '{label}', each evaluating how directly their research axis contributes to mitigating bioterrorist threats on a scale from 0 to 1, where 0 indicates no direct contribution and 1 indicates a direct and substantial contribution to reducing the threat.    Research Axis: '{label}'    Each expert provides a score answering the question: "How directly does your research axis contribute to reducing the bioterrorist threat of type [type]?"    Please provide five scores for each expert, corresponding to the following threat types:    1. Viral Threats    2. Bacterial Threats    3. Toxin-Based Threats    4. Fungal Threats    5. Prion-Based Threats    Format the response exactly as follows:    Expert 1: Viral - X, Bacterial - X, Toxin - X, Fungal - X, Prion - X    Expert 2: Viral - X, Bacterial - X, Toxin - X, Fungal - X, Prion - X    ...    Expert 10: Viral - X, Bacterial - X, Toxin - X, Fungal - X, Prion - X    """    response = client.chat.completions.create(        model="gpt-4-turbo",        messages=[{"role": "user",                    "content": prompt}],        temperature=0.0,        stop=["\n\n"])        #max_tokens=60        #stop=["\n"])    return response.choices[0].message.contentimport redef extract_scores(output):    # Define a dictionary to hold all scores    scores = {        'Viral': [],        'Bacterial': [],        'Toxin': [],        'Fungal': [],        'Prion': []    }    # Regular expression to find scores    score_pattern = r"Expert \d+: Viral - (\d\.\d+), Bacterial - (\d\.\d+), Toxin - (\d\.\d+), Fungal - (\d\.\d+), Prion - (\d\.\d+)"    # Find all matches and iterate over them    for match in re.finditer(score_pattern, output):        scores['Viral'].append(float(match.group(1)))        scores['Bacterial'].append(float(match.group(2)))        scores['Toxin'].append(float(match.group(3)))        scores['Fungal'].append(float(match.group(4)))        scores['Prion'].append(float(match.group(5)))    return scores# Example of calling the function for a specific research axis and threat typescores_string = evaluate_leverage_axis_problems(cluster_labels[1])print("Scores:", extract_scores(scores_string))clusters_problems_scores = {}for cluster, label in cluster_labels.items():    clusters_problems_scores[cluster] = extract_scores(evaluate_leverage_axis_problems(label))# Calculate the median scores and check against the thresholdthreshold = 0.85cluster_median_scores = {}problems_above_threshold = {}for cluster, scores in clusters_problems_scores.items():    medians = {}    threats_above_threshold = []        for threat, values in scores.items():        med_score = np.median(values)        medians[threat] = med_score        if med_score > threshold:            threats_above_threshold.append(threat)        cluster_median_scores[cluster] = medians    problems_above_threshold[cluster] = threats_above_threshold### Étape 7 : Enregistrer les résultats #### Clusters et embeddingsdata = {    'Paper ID': [paper['paperId'] for paper in papers_en if 'abstract' in paper],    'Cluster Label': labels}for dim in range(n_dims):    data[f't-SNE Dim {dim + 1}'] = embeddings_tSNE[:, dim]results_df = pd.DataFrame(data)results_df.to_csv('outputs_bioterrorism/paper_embeddings_clusters.csv', index=False)# Intitulésdf = pd.DataFrame(list(cluster_labels.items()), columns=['Cluster_ID', 'Cluster_Name'])df.to_csv('outputs_bioterrorism/cluster_labels.csv', index=False)# Évaluations de l'influence entre chaque axe et chaque problème concretdata_for_csv = []for cluster, threats in clusters_problems_scores.items():    for threat, scores in threats.items():        for score in scores:            data_for_csv.append({                'Cluster': cluster,                'Threat Type': threat,                'Score': score            })df = pd.DataFrame(data_for_csv)df.to_csv('outputs_bioterrorism/cluster_problem_scores.csv', index=False)# # Problèmes concrets associés à chaque axe# df = pd.DataFrame(list(problems_above_threshold.items()), columns=['Cluster', 'Associated problems'])# df.to_csv('outputs_bioterrorism/cluster_problems.csv', index=False)