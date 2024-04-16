# %%
import pydantic
import pathlib
import csv
import networkx as nx
import itertools
from IPython.display import display
import PIL.Image
import textwrap

class TNSE(pydantic.BaseModel):
    class PaperPoint(pydantic.BaseModel):
        paper_id: str
        cluster_label: int
        x: float
        y: float
        z: float
    points: dict[str, PaperPoint]

with open('./outputs_bioterrorism/paper_embeddings_clusters.csv', newline='') as csvfile:
    reader = csv.DictReader(csvfile)
    tnse = TNSE(points={i['Paper ID']: TNSE.PaperPoint(paper_id=i['Paper ID'], cluster_label=i['Cluster Label'], x=i['t-SNE Dim 1'], y=i['t-SNE Dim 2'], z=i['t-SNE Dim 3']) for i in reader})


# %%
class Citations(pydantic.BaseModel):
    class Citation(pydantic.BaseModel):
        class PaperRef(pydantic.BaseModel):
            paperId: str | None = None
        currentPaper: PaperRef | None = None
        citedPaper: PaperRef
        intents: list[str]
        isInfluential: bool
    citations: list[Citation]

class J(pydantic.BaseModel):
    p: dict[str, Citations]

class Papers(pydantic.BaseModel):
    class Paper(pydantic.BaseModel):
        paperId: str
        title: str
        referenceCount: int
        citationCount: int
        influentialCitationCount: int
        fieldsOfStudy: list | None
        s2FieldsOfStudy: list
        publicationTypes: list[str] | None

        class Journal(pydantic.BaseModel):
            name: str | None = None
            volume: str | None = None
        journal: Journal | None
        
    papers: dict[str, Paper]

allPapers = Papers.model_validate_json(pathlib.Path('./outputs_bioterrorism/allPapers.json').read_text()).papers
allCitationsOutbond = J.model_validate_json(pathlib.Path('./outputs_bioterrorism/allCitations.json').read_text()).p

# Filter for citations that are in bioterrorism papers
allCitations = {k: v for k, v in allCitationsOutbond.items() for cit in v.citations if cit.citedPaper.paperId in allPapers}

for k, v in allCitations.items():
    for cit in v.citations:
        cit.currentPaper = Citations.Citation.PaperRef(paperId=k)

allCitations

# %%
clusters_link = dict()
clusters_link

for src, links in allCitations.items():
    for link in links.citations:
        trg = link.citedPaper.paperId
        if any(i not in tnse.points for i in [src, trg]):
            continue
        srcClass = tnse.points[src].cluster_label
        trgClass = tnse.points[trg].cluster_label
        if any(i == -1 for i in [srcClass, trgClass]):
            continue
        clusters_link.setdefault((srcClass, trgClass), []).append(link)
# %%
pc = dict()

with open('./outputs_bioterrorism/cluster_problem_scores.csv') as csvfile:
    reader = csv.DictReader(csvfile)
    while True:
        ten_experts = list(sorted(itertools.islice(reader, 10), key=lambda i: float(i['Score'])))
        if not ten_experts:
            break
        c = pc.setdefault(int(ten_experts[0]['Cluster']), dict())
        c[ten_experts[0]['Threat Type']] = (float(ten_experts[4]['Score']) + float(ten_experts[5]['Score'])) / 2
pc

# %%
def keep(edge):
    if edge[0] == edge[1]:
        return False

    dat = clusters_link.get(edge)
    if not dat:
        return False

    return any(i.isInfluential for i in dat) or len({i.citedPaper.paperId for i in dat}) >= 3

with open('./outputs_bioterrorism/cluster_labels.csv') as csvfile:
    reader = csv.DictReader(csvfile)
    clusters = {int(i['Cluster_ID']): '\n'.join(textwrap.wrap(i['Cluster_Name'], width=20)) for i in reader}

clusters_num = clusters.keys() 
clusters_num = [src for src in clusters_num if any(keep((src, trg)) for trg in clusters_num if src != trg)]
cluster_graph = nx.DiGraph()
cluster_graph.add_nodes_from(clusters_num)

colors_dict = {
    "Viral": "red",
    "Bacterial": "green",
    "Toxin": "blue",
    "Fungal": "yellow",
    "Prion": "purple",
}

for (src, trg), dat in clusters_link.items():
    allSrcs = {i.currentPaper.paperId for i in dat}
    allTrgs = {i.citedPaper.paperId for i in dat}
    #if not keep((src, trg)):
        #continue

    cluster_graph.add_edge(src, trg, data=dat)


def get_attr(edge):
    dat = clusters_link[edge]
    allTrgs = {i.citedPaper.paperId for i in dat}

    influential = any(i.isInfluential for i in dat)
    alpha = 1 if keep(edge) else 0

    color = "black"

    return dict(
        penwidth=min(len(allTrgs), 5) / 2 if not influential else 5,
        constraint=keep(edge),
        color=f'{color} {alpha:.3f}' if alpha > 0.1 else 'transparent',
    )

draw_graph = cluster_graph
nx.set_edge_attributes(draw_graph, {edge: get_attr(edge) for edge in draw_graph.edges})

def get_attr_pc(cluster, cat):
    score = pc[cluster][cat]

    assert colors_dict.get(cat) is not None or score < 0.85

    return dict(
        style = 'invis' if score < 0.85 else 'dashed',
        color=colors_dict.get(cat),
        constraint=True,
        weight=1000 if score > 0.85 else 1,
    )

def get_colors(cluster):
    colors =[colors_dict[k] for k, score in pc[cluster].items() if score > 0.85]
    return dict(
        fillcolor=':'.join(colors),
        style='wedged' if len(colors) > 1 else 'filled',
    )

nx.set_node_attributes(draw_graph, {c: get_colors(c) for c in pc})

draw_graph = draw_graph.subgraph(clusters_num)
draw_graph = nx.relabel_nodes(cluster_graph, clusters)

graphviz = nx.nx_agraph.to_agraph(draw_graph)
graphviz.graph_attr.update()
graphviz.node_attr.update(fontsize=40)
graphviz.edge_attr.update(dir='back')
graphviz.draw('./outputs_bioterrorism/cluster_graph.png', prog='dot')
display(PIL.Image.open('./outputs_bioterrorism/cluster_graph.png'))


# %%
