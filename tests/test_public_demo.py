import gzip
import json
import re
import subprocess
from pathlib import Path

import pytest

from citeprobe.evaluation_models import EvaluationOutput
from scripts import audit_demo_key
from scripts.export_public_demo import export

ROOT = Path("artifacts/empirical-pilot-immediate-001")


def test_export_matches_evaluation_and_has_no_private_fields() -> None:
    data = json.loads(Path("public-demo/data.json").read_bytes())
    evaluation = EvaluationOutput.model_validate_json(
        (ROOT / "a-empirical-evaluation-001/evaluation.json").read_bytes()
    )
    assert data["review_status"] == "owner_review_pending"
    assert data == export()
    assert len(data["papers"]) == 8
    for paper in data["papers"]:
        for provider in ("openalex", "crossref"):
            expected = next(
                r
                for r in evaluation.lookups
                if r.source_id == "arxiv:" + paper["id"] and r.provider == provider
            )
            result = paper["results"][provider]
            assert result["outcome"] == expected.outcome
            assert result["recall_at_5"] == expected.recall_at_5
            assert [c["rank"] for c in result["candidates"]] == [
                c.candidate.provider_rank for c in expected.candidates
            ]
            assert [c["judgment"] for c in result["candidates"]] == [
                c.judgment for c in expected.candidates
            ]
    contents = json.dumps(data).lower()
    assert not re.search(r"(?:api[_-]?key|authorization|access[_-]?token)\s*[:=]", contents)
    assert all(k not in contents for k in ('"abstract"', '"email"', '"raw"'))


def test_render_filter_detail_and_error_states() -> None:
    data = Path("public-demo/data.json").read_text(encoding="utf-8")
    app = Path("public-demo/app.js").read_text(encoding="utf-8")
    harness = r"""
const vm = require('vm');
class Node {
  constructor(tag='div') {
    this.tag=tag;this.children=[];this.dataset={};this.style={};this.attrs={};
    this.textContent='';this.classList={toggle:()=>{}};
  }
  append(...nodes){this.children.push(...nodes)}
  replaceChildren(...nodes){this.children=[...nodes]}
  setAttribute(k,v){this.attrs[k]=v}
  addEventListener(k,v){this[k]=v}
  showModal(){this.open=true}
  close(){this.open=false}
}
const ids = {};
for(const id of ['papers','comparison','paper-count','detail','detail-content','close-detail'])
  ids[id]=new Node();
const buttons=['all','1-7','8-14','15-30','31-60'].map(v=>{
  const x=new Node('button');x.dataset.cohort=v;return x;
});
global.document={getElementById:id=>ids[id],querySelectorAll:()=>buttons,
  createElement:t=>new Node(t)};
global.fetch=()=>Promise.resolve({ok:true,json:()=>Promise.resolve(DATA)});
vm.runInThisContext(APP);
setImmediate(()=>{
  if(ids.papers.children.length!==8 || ids.comparison.children.length!==2) throw Error('render');
  buttons[1].click(); if(ids.papers.children.length!==2) throw Error('filter');
  ids.papers.children[0].click();
  if(!ids.detail.open || ids['detail-content'].children.length<4) throw Error('detail');
  const nested=ids['detail-content'].children.flatMap(n=>n.children).flatMap(n=>n.children);
  if(!nested.some(y=>String(y.textContent).includes('UNDETERMINED'))) throw Error('judgment');
  ids['close-detail'].click(); if(ids.detail.open) throw Error('close');
  console.log('render, filter, candidate inspection, and close passed');
});
"""
    script = harness.replace("DATA", data).replace("APP", json.dumps(app))
    result = subprocess.run(
        ["node", "-"], input=script, text=True, encoding="utf-8", capture_output=True, check=True
    )
    assert "candidate inspection" in result.stdout


def test_secret_scanner_detects_compressed_and_encoded_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "synthetic-secret-key-0123456789"
    (tmp_path / "response.bin").write_bytes(gzip.compress(secret.encode(), mtime=0))
    monkeypatch.setattr(audit_demo_key, "DIRECTORIES", (tmp_path,))
    count, matches = audit_demo_key.scan(secret)
    assert count == 1 and matches == [str(tmp_path / "response.bin")]


def test_env_key_is_read_without_executing_file(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text('OPENALEX_API_KEY="short-test-key"\n', encoding="utf-8")
    assert audit_demo_key.read_env_key(path) == "short-test-key"
    path.write_text("OPENALEX_API_KEY=one\nOPENALEX_API_KEY=two\n", encoding="utf-8")
    with pytest.raises(ValueError, match="exactly one"):
        audit_demo_key.read_env_key(path)
    path.write_text("OTHER=value\n", encoding="utf-8")
    with pytest.raises(ValueError, match="exactly one"):
        audit_demo_key.read_env_key(path)


def test_audit_rejects_empty_and_placeholder_keys(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="empty"):
        audit_demo_key.scan("")
    with pytest.raises(ValueError, match="placeholder"):
        audit_demo_key.scan("your-key-here")


def test_audit_accepts_nonempty_short_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "evidence.txt").write_text("contains short-key", encoding="utf-8")
    monkeypatch.setattr(audit_demo_key, "DIRECTORIES", (tmp_path,))
    _, matches = audit_demo_key.scan("short-key")
    assert matches == [str(tmp_path / "evidence.txt")]


def test_data_load_error_state() -> None:
    app = Path("public-demo/app.js").read_text(encoding="utf-8")
    harness = r"""
const vm = require('vm');
const ids = {};
for (const id of ['papers','comparison','paper-count','detail','detail-content','close-detail'])
  ids[id] = {children:[], addEventListener(){}, replaceChildren(...x){this.children=x}};
global.document={getElementById:id=>ids[id], querySelectorAll:()=>[],
  createElement:()=>({className:'',textContent:''})};
global.fetch=()=>Promise.reject(Error('offline'));
vm.runInThisContext(APP);
setImmediate(()=>{
  if (!ids.papers.children[0].textContent.includes('could not be loaded')) throw Error('error');
  console.log('error state passed');
});
"""
    result = subprocess.run(
        ["node", "-"],
        input=harness.replace("APP", json.dumps(app)),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )
    assert "error state passed" in result.stdout
