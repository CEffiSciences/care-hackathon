import pathlib
import pydantic
import requests
import json
import os
from tqdm import tqdm

api_key = pathlib.Path('.semantic_key').read_text().strip()

# %%
def semantic(url, params, continuation=lambda x: None, update_params=lambda c: {}):
    call = None
    results = []
    
    while call is None or continuation(call):
        call = requests.get(
            url,
            headers={ "x-api-key": api_key },
            params=params | (update_params(call) if call is not None else {}),
        
        ).json()
        results += call['data']
        
    return results


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
     

allPapers = Papers(papers={v['paperId']: v for v in semantic(
    url='https://api.semanticscholar.org/graph/v1/paper/search/bulk',
    params=dict(
        query="bioterrorism",
        fields=','.join(Papers.Paper.model_fields.keys()),
    ),
    continuation=lambda c: c.get('token'),
    update_params=lambda c: {'token': c['token']}
    )})

# %%
allCitations = {}

class Citations(pydantic.BaseModel):
    class Citation(pydantic.BaseModel):
        class PaperRef(pydantic.BaseModel):
            paperId: str | None = None
        citedPaper: PaperRef
        intents: list[str]
        isInfluential: bool
    citations: list[Citation]


for ix, (k, v) in enumerate(tqdm([i for i in allPapers.papers.items() if i[0] not in allCitations])):
    citations = Citations(citations=semantic(
        url=f'https://api.semanticscholar.org/graph/v1/paper/{v.paperId}/references',
        params=dict(
            fields='paperId,intents,isInfluential'
        ),
    ))
    
    allCitations[k] = citations

# %%
class J(pydantic.BaseModel):
    p: dict[str, Citations]

j = J(p=allCitations)

# %%
with open('./allCitations.json', 'w') as f:
    f.write(j.model_dump_json())
with open('./allPapers.json', 'w') as f:
    f.write(allPapers.model_dump_json())
