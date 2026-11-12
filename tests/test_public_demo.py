import gzip
import json
import re
import subprocess
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.request import urlopen

import pytest

from citeprobe.evaluation_models import EvaluationOutput
from scripts import audit_demo_key, export_public_demo
from scripts.export_public_demo import export

ROOT = Path("artifacts/empirical-pilot-immediate-001")


def test_static_root_serves_public_export() -> None:
    root = Path("public-demo")
    assert {p.name for p in root.iterdir()} == {
        "index.html",
        "methodology.html",
        "style.css",
        "refine.css",
        "integrated.css",
        "app.js",
        "integrated.js",
        "data.json",
        "experiment-manifest.json",
        "verify.py",
        "fonts",
    }
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "public-demo/data.json"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert tracked.stdout.strip() == "public-demo/data.json"
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(root))
    )
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with urlopen(f"http://127.0.0.1:{server.server_port}/data.json", timeout=5) as response:
            assert response.status == 200
            assert response.headers.get_content_type() == "application/json"
            assert json.load(response) == export()
    finally:
        server.shutdown()
        worker.join(timeout=5)
        server.server_close()


def test_export_matches_evaluation_and_has_no_private_fields() -> None:
    data = json.loads(Path("public-demo/data.json").read_bytes())
    evaluation = EvaluationOutput.model_validate_json(
        (ROOT / "a-empirical-evaluation-001/evaluation.json").read_bytes()
    )
    assert data["review_status"] == "owner_approved"
    assert data == export()
    assert set(data) == {
        "schema_version",
        "review_status",
        "evaluation_id",
        "dataset_sha256",
        "papers",
    }
    assert len(data["papers"]) == 8
    for paper in data["papers"]:
        assert set(paper) == {"id", "title", "authors", "cohort", "results"}
        assert set(paper["results"]) == {"openalex", "crossref"}
        for provider in ("openalex", "crossref"):
            expected = next(
                r
                for r in evaluation.lookups
                if r.source_id == "arxiv:" + paper["id"] and r.provider == provider
            )
            result = paper["results"][provider]
            assert set(result) == {
                "outcome",
                "recall_at_1",
                "recall_at_5",
                "rank_one_judgment",
                "candidates",
            }
            for candidate in result["candidates"]:
                assert set(candidate) == {
                    "rank",
                    "title",
                    "authors",
                    "year",
                    "doi",
                    "arxiv_id",
                    "judgment",
                    "reason",
                }
            assert result["outcome"] == expected.outcome
            assert result["recall_at_1"] == expected.recall_at_1
            assert result["recall_at_5"] == expected.recall_at_5
            assert result["rank_one_judgment"] == expected.rank_one_judgment
            assert [c["rank"] for c in result["candidates"]] == [
                c.candidate.provider_rank for c in expected.candidates
            ]
            assert [c["judgment"] for c in result["candidates"]] == [
                c.judgment for c in expected.candidates
            ]
            assert [c["reason"] for c in result["candidates"]] == [
                c.reason for c in expected.candidates
            ]
    contents = json.dumps(data).lower()
    assert not re.search(r"(?:api[_-]?key|authorization|access[_-]?token)\s*[:=]", contents)
    assert all(k not in contents for k in ('"abstract"', '"email"', '"raw"'))


def test_frozen_validation_routes_and_provider_selection() -> None:
    app = Path("public-demo/app.js").read_text(encoding="utf-8")
    data = Path("public-demo/data.json").read_text(encoding="utf-8")
    manifest = Path("public-demo/experiment-manifest.json").read_text(encoding="utf-8")
    harness = r"""
const vm = require('vm'), assert = require('node:assert/strict');
vm.runInThisContext(APP);
const data=DATA, manifest=MANIFEST;
assert.equal(validate(data).length,8);
assert.equal(validateManifest(manifest,data).length,16);
assert.deepEqual(readRoute('#paper=2611.07721&provider=crossref'),
  {id:'2611.07721',provider:'crossref'});
assert.equal(readRoute('#findings').id,null);
assert.equal(selectedProvider(data.papers[0],null),'crossref');
assert.equal(selectedProvider(data.papers[0],'openalex'),'openalex');
assert.equal(selectedProvider(data.papers[0],'invalid'),'crossref');
for(const field of ['evaluation_id','dataset_sha256']){
 assert.throws(()=>validateManifest({...manifest,[field]:'wrong'},data));
}
assert.throws(()=>validateManifest({...manifest,searches:manifest.searches.slice(1)},data));
const malformed=structuredClone(manifest);malformed.searches[0].authentication_mode='unknown';
assert.throws(()=>validateManifest(malformed,data));
for(const review_status of ['owner_review_pending','unknown'])
 assert.throws(()=>validate({...data,review_status}));
console.log('validation and routing passed');
"""
    script = harness.replace("APP", json.dumps(app)).replace("DATA", data)
    script = script.replace("MANIFEST", manifest)
    result = subprocess.run(
        ["node", "-"], input=script, text=True, encoding="utf-8", capture_output=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "routing passed" in result.stdout


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


@pytest.mark.parametrize(
    "response",
    [
        "Promise.reject(Error('offline'))",
        "Promise.reject(Error('timeout'))",
        "Promise.resolve({ok:false,status:404})",
        "Promise.resolve({ok:false,status:429})",
        "Promise.resolve({ok:false,status:500})",
        "Promise.resolve({ok:true,json:()=>Promise.reject(Error('invalid JSON'))})",
        "Promise.resolve({ok:true,json:()=>Promise.resolve({})})",
        "Promise.resolve({ok:true,json:()=>Promise.resolve({papers:[]})})",
    ],
)
def test_data_load_error_state(response: str) -> None:
    assert_error_state(response)


def assert_error_state(response: str) -> None:
    app = Path("public-demo/app.js").read_text(encoding="utf-8")
    harness = r"""
const vm=require('vm');
const ids={};
for(const id of ['#overview','#inspection','#loading','#cohort'])
 ids[id]={hidden:false,children:[],addEventListener(){},setAttribute(k,v){this[k]=v},
 replaceChildren(...items){this.children=items}};
global.document={querySelector:id=>ids[id],createElement:tag=>({textContent:'',tag})};
global.window={addEventListener(){}};
global.fetch=()=>RESPONSE;
vm.runInThisContext(APP);
setImmediate(()=>{
 if(!ids['#overview'].hidden || !ids['#inspection'].hidden)throw Error('stale evidence');
 if(!ids['#loading'].children[0].textContent.includes('could not be loaded'))throw Error('error');
 if(ids['#loading'].role!=='alert' || !ids['#cohort'].disabled)throw Error('feedback');
 console.log('error state passed');
});
"""
    result = subprocess.run(
        ["node", "-"],
        input=harness.replace("APP", json.dumps(app)).replace("RESPONSE", response),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )
    assert "error state passed" in result.stdout


@pytest.mark.parametrize("change", ["authors", "rank", "identity", "bounds", "duplicate"])
def test_invalid_nested_records_fail_before_render(change: str) -> None:
    data = json.loads(Path("public-demo/data.json").read_bytes())
    result = data["papers"][0]["results"]["crossref"]
    if change == "authors":
        result["candidates"][0]["authors"] = "malformed author list"
    elif change == "rank":
        result["candidates"][0]["rank"] = 0
    elif change == "identity":
        result["candidates"][0]["judgment"] = "CORRECT"
    elif change == "bounds":
        result["recall_at_5"] = "HIT"
    else:
        data["papers"][1]["id"] = data["papers"][0]["id"]
    response = "Promise.resolve({ok:true,json:()=>Promise.resolve(" + json.dumps(data) + ")})"
    assert_error_state(response)


def test_export_rejects_changed_frozen_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    changed = tmp_path / "dataset.json"
    changed.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(export_public_demo, "FROZEN_SHA256", {changed: "0" * 64})
    with pytest.raises(ValueError, match="Frozen input checksum mismatch"):
        export()


def test_publication_copy_matches_export_status() -> None:
    for name in ("index.html", "methodology.html"):
        html = Path("public-demo", name).read_text(encoding="utf-8")
        assert "RESEARCH PILOT" in html
        assert "PRIVATE PREVIEW" not in html
        assert "review pending" not in html.lower()
        assert "pending owner" not in html.lower()
    methods = Path("public-demo/methodology.html").read_text(encoding="utf-8")
    assert "not that a paper is missing from a database" in methods
    assert "eight-paper sample does not support population-level conclusions" in methods
    assert "Original raw responses and credentials are excluded" in methods


def test_publication_copy_avoids_licensing_claims() -> None:
    paths = [
        Path("public-demo/index.html"),
        Path("public-demo/methodology.html"),
        Path("README.md"),
        Path("docs/public-demo.md"),
        Path("pyproject.toml"),
    ]
    for path in paths:
        copy = path.read_text(encoding="utf-8")
        assert not re.search(r"open[- ]source", copy, re.IGNORECASE), path
    homepage = paths[0].read_text(encoding="utf-8")
    assert "Research prototype in progress" not in homepage
    assert "RESEARCH PILOT" in homepage
