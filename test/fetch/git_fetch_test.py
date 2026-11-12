#!/usr/bin/env python3
# Tests for git repositories as the url of a library path (git+https://<host>/<repo>:<namespace>/<name>[@<version>][:<hash>]): c3c talks to a local fixture server, no network is used.
# Usage: python3 test/fetch/git_fetch_test.py <path-to-c3c>
import hashlib
import http.server
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import zipfile

LIB_SOURCE = "module mylib;\nfn int one() => 1;\n"
APP_SOURCE = "module app;\nimport std::io;\nimport mylib;\nfn void main()\n{\n\tio::printfn(\"one=%d\", mylib::one());\n}\n"
# Known answer of the content hash, computed once with the reference implementation of c3l.
KAT_FILES = {"manifest.json": b'{"provides":"kat"}', "src/a.c3": b"module a;\n", ".gitkeep": b"", "b.txt": b"hello"}
KAT_HASH = "d3870beadfe5b3de73ffbf0c9ee0e64c1bc2b8329d1898fef2be3760e3f30bdc"
COMMIT = "0123456789abcdef0123456789abcdef01234567"
GH = "git+https://github.com/o/r"


def make_zip(files, top=None):
	"""A zip of {path: bytes}; with `top` every path is below that directory, which has an entry of its own."""
	buf = io.BytesIO()
	with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
		if top:
			z.writestr(top + "/", b"")
		for name, data in files.items():
			z.writestr((top + "/" if top else "") + name, data)
	return buf.getvalue()


def lib_files(name="mylib", extra=None, dependencies=None):
	manifest = {"provides": name, "sources": ["src"]}
	if dependencies:
		manifest["dependencies"] = dependencies
	files = {
		"manifest.json": json.dumps(manifest).encode(),
		"src/%s.c3" % name: LIB_SOURCE.replace("mylib", name).encode(),
	}
	files.update(extra or {})
	return files


def content_hash(data):
	"""The content hash of a source archive: sha256 over the files without the top directory, sorted by path,
	each as path, 0 byte, size (8 bytes little-endian), data."""
	z = zipfile.ZipFile(io.BytesIO(data))
	names = [i.filename for i in z.infolist() if not i.is_dir()]
	tops = {n.split("/", 1)[0] for n in names}
	assert len(tops) == 1, tops
	pre = tops.pop() + "/"
	h = hashlib.sha256()
	for name, real in sorted((n[len(pre):], n) for n in names):
		d = z.read(real)
		h.update(name.encode() + b"\0" + len(d).to_bytes(8, "little") + d)
	return h.hexdigest()


class Handler(http.server.BaseHTTPRequestHandler):
	routes = {}
	requests = []

	def do_GET(self):
		Handler.requests.append(self.path)
		data = Handler.routes.get(self.path)
		if data is None:
			self.send_response(404)
			self.end_headers()
			return
		self.send_response(200)
		self.send_header("Content-Length", str(len(data)))
		self.end_headers()
		self.wfile.write(data)

	def log_message(self, *args):
		pass


class Runner:
	def __init__(self, c3c, base_url, root):
		self.c3c = c3c
		self.base_url = base_url
		self.root = root
		self.n = 0

	def project(self, dependencies=None):
		self.n += 1
		d = os.path.join(self.root, "p%d" % self.n)
		os.makedirs(os.path.join(d, "src"))
		project = {"dependency-search-paths": ["lib"], "targets": {"app": {"type": "executable", "sources": ["src/**"]}}}
		if dependencies:
			project["dependencies"] = dependencies
		with open(os.path.join(d, "project.json"), "w") as f:
			json.dump(project, f)
		with open(os.path.join(d, "src", "main.c3"), "w") as f:
			f.write(APP_SOURCE)
		return d

	def run(self, cwd, *args, url=True):
		env = {k: v for k, v in os.environ.items() if "proxy" not in k.lower()}
		env["no_proxy"] = "127.0.0.1,localhost"
		cmd = [self.c3c] + (["--git-base-url", self.base_url] if url else []) + list(args)
		p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=300)
		return p.returncode, p.stdout + p.stderr

	def dependencies(self, cwd):
		with open(os.path.join(cwd, "project.json")) as f:
			return json.load(f).get("dependencies", [])


def route(path, data):
	Handler.routes[path] = data


def reset():
	Handler.routes.clear()
	Handler.requests.clear()


def main():
	if len(sys.argv) != 2:
		print(__doc__)
		return 2
	server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
	threading.Thread(target=server.serve_forever, daemon=True).start()
	root = tempfile.mkdtemp(prefix="c3c-git-")
	runner = Runner(os.path.abspath(sys.argv[1]), "http://127.0.0.1:%d" % server.server_port, root)
	failures = []
	count = 0

	def check(name, cond, output=""):
		nonlocal count
		count += 1
		if not cond:
			failures.append(name)
			print("FAIL: %s\n%s" % (name, output))
		else:
			print("ok:   %s" % name)

	def fetch(d, *args):
		return runner.run(d, "fetch", *args)

	lib_dir = lambda d: os.path.join(d, "lib", "mylib.c3l")
	installed = lambda d: os.path.isdir(os.path.join(d, "lib")) and bool(os.listdir(os.path.join(d, "lib")))

	archive = make_zip(lib_files(extra={".github/ci.yml": b"x", "src/.hidden/y.c3": b"x", ".gitkeep": b"", "empty.txt": b""}), top="r-1.0")
	archive_hash = content_hash(archive)

	# Known answer of the content hash, both in the test and in c3c.
	check("content hash: known answer", content_hash(make_zip(KAT_FILES, top="kat-1")) == KAT_HASH)
	reset()
	route("/github.com/o/r/archive/v1.zip", make_zip(KAT_FILES, top="kat-1"))
	d = runner.project()
	code, out = fetch(d, GH + "@v1")
	check("content hash: known answer in c3c", code == 0 and "pin: %s:o/kat@v1:%s" % (GH, KAT_HASH) in out, out)

	# The three hosts.
	reset()
	route("/github.com/o/r/archive/v1.zip", archive)
	d = runner.project()
	code, out = fetch(d, GH + "@v1")
	check("github.com: tag", code == 0 and os.path.isfile(os.path.join(lib_dir(d), "manifest.json")) and Handler.requests == ["/github.com/o/r/archive/v1.zip"], out + str(Handler.requests))
	check("pin line", "pin: %s:o/mylib@v1:%s" % (GH, archive_hash) in out, out)
	check("name from 'provides' is recorded", runner.dependencies(d) == ["%s:o/mylib@v1:%s" % (GH, archive_hash)], str(runner.dependencies(d)))
	check("archive: dot paths skipped", not os.path.exists(os.path.join(lib_dir(d), ".github")) and not os.path.exists(os.path.join(lib_dir(d), ".gitkeep"))
		  and not os.path.exists(os.path.join(lib_dir(d), "src", ".hidden")))
	check("archive: other files kept", os.path.isfile(os.path.join(lib_dir(d), "src", "mylib.c3")) and os.path.isfile(os.path.join(lib_dir(d), "empty.txt")))
	reset()
	route("/codeberg.org/o/r/archive/v2.zip", archive)
	code, out = fetch(runner.project(), "git+https://codeberg.org/o/r.git@v2")
	check("codeberg.org: tag, .git dropped", code == 0 and "pin: git+https://codeberg.org/o/r:o/mylib@v2:" in out, out)
	reset()
	route("/gitlab.com/g/sub/r/-/archive/v3/r-v3.zip", archive)
	d = runner.project()
	code, out = fetch(d, "git+https://gitlab.com/g/sub/r@v3")
	check("gitlab.com: subgroup", code == 0 and "pin: git+https://gitlab.com/g/sub/r:g/sub/mylib@v3:" in out, out)
	reset()
	route("/gitlab.com/g/r/-/archive/v3/r-v3.zip", archive)
	code, out = fetch(runner.project(), "git+https://gitlab.com/g/r@v3")
	check("gitlab.com: two segments", code == 0, out)

	# Commit, HEAD and no ref.
	reset()
	route("/github.com/o/r/archive/%s.zip" % COMMIT, archive)
	code, out = fetch(runner.project(), GH + "@" + COMMIT)
	check("commit", code == 0 and "pin: %s:o/mylib@%s:%s" % (GH, COMMIT, archive_hash) in out, out)
	reset()
	route("/github.com/o/r/archive/HEAD.zip", archive)
	for path in (GH + "@HEAD", GH):
		d = runner.project()
		code, out = fetch(d, path)
		check("%s: warning, no pin" % path, code == 0 and "not pinned, the library follows the default branch" in out and "pin:" not in out, out)
		check("%s: recorded without a hash" % path, runner.dependencies(d) == [GH + ":o/mylib" + path[len(GH):]], str(runner.dependencies(d)))
	check("no ref asks for HEAD", Handler.requests[-1] == "/github.com/o/r/archive/HEAD.zip", str(Handler.requests))

	# A typed name.
	reset()
	route("/github.com/o/r/archive/v1.zip", archive)
	d = runner.project()
	code, out = fetch(d, "%s:o/mylib@v1" % GH)
	check("typed name matches", code == 0 and os.path.isdir(lib_dir(d)), out)
	d = runner.project()
	code, out = fetch(d, "%s:o/other@v1" % GH)
	check("typed name mismatch", code != 0 and "provides 'mylib', not 'other'" in out and not installed(d), out)
	code, out = fetch(d, "%s:x/mylib@v1" % GH)
	check("namespace mismatch", code != 0 and "the namespace must be 'o'" in out and not installed(d), out)
	code, out = fetch(d, "git+https://gitlab.com/g/sub/r:g/mylib@v1")
	check("namespace mismatch, subgroup", code != 0 and "the namespace must be 'g/sub'" in out, out)
	route("/github.com/o/r/archive/HEAD.zip", archive)
	d = runner.project()
	code, out = fetch(d, GH)
	check("short form without a version", code == 0 and "pin:" not in out, out)

	# Refused paths.
	d = runner.project()
	code, out = runner.run(d, "fetch", "git+https://example.com/o/r")
	check("unsupported host", code != 0 and "unsupported git host 'example.com' (supported: github.com, codeberg.org, gitlab.com)" in out, out)
	for bad, text in [("git+http://github.com/o/r", "only git+https://"), ("git+ssh://github.com/o/r:o/r", "only git+https://"),
					  ("git://github.com/o/r", "Skipping invalid"), ("git+https://github.com/o/r?x=1", "invalid repository path"),
					  ("git+https://github.com/o/r%2e", "invalid repository path"), ("git+https://github.com/o/../r", "invalid repository path"),
					  ("git+https://github.com/o", "must have 2 segments"), ("git+https://github.com/o/r/x", "must have 2 segments"),
					  ("git+https://gitlab.com/g", "must have 2 or more segments"),
					  (GH + "@a/b", "invalid version 'a/b'"), (GH + "@", "invalid version ''"),
					  (GH + "#v1", "invalid repository path"), (GH + "@v1#x", "invalid version 'v1#x'"), (GH + ":o/mylib#x", "invalid"),
					  (GH + ":o/my#lib", "invalid"), (GH + "@v1:" + "a" * 64 + "x", "Skipping invalid"),
					  (GH + ":" + "a" * 64, "a checksum requires a version"), (GH + ":o/mylib:" + "a" * 64, "a checksum requires a version"),
					  (GH + "@HEAD:" + "a" * 64, "a checksum is not allowed with HEAD"), (GH + ":o/mylib@HEAD:" + "a" * 64, "a checksum is not allowed with HEAD"),
					  (GH + ":o/Bad@v1", "invalid library name 'Bad'")]:
		code, out = fetch(d, bad)
		check("refused: " + bad, code != 0 and text in out and not installed(d), out)

	# A missing name in a project or manifest.
	hint = "write it as git+https://github.com/o/toml.c3l:o/toml[@<version>]"
	d = runner.project(["git+https://github.com/o/toml.c3l"])
	code, out = runner.run(d, "project", "fetch")
	check("project.json: hint for the missing name", code != 0 and hint in out, out)
	code, out = runner.run(d, "build", url=False)
	check("build: hint for the missing name", code != 0 and hint in out, out)
	d = runner.project(["git+https://github.com/o/toml.c3l@v1"])
	code, out = runner.run(d, "project", "fetch")
	check("project.json: hint with a version", code != 0 and hint in out, out)

	# Content hash.
	reset()
	route("/github.com/o/r/archive/v1.zip", archive)
	d = runner.project()
	code, out = fetch(d, "%s@v1:%s" % (GH, archive_hash))
	check("content hash ok", code == 0 and os.path.isdir(lib_dir(d)), out)
	d = runner.project()
	code, out = fetch(d, "%s:o/mylib@v1:%s" % (GH, archive_hash))
	check("content hash ok, full form", code == 0 and os.path.isdir(lib_dir(d)), out)
	d = runner.project()
	code, out = fetch(d, "%s@v1:%s" % (GH, "0" * 64))
	check("content hash mismatch", code != 0 and "content hash mismatch (expected %s, got %s)" % ("0" * 64, archive_hash) in out and not installed(d), out)

	# Bad archives.
	reset()
	route("/github.com/o/r/archive/v1.zip", make_zip(lib_files()))
	d = runner.project()
	code, out = fetch(d, GH + "@v1")
	check("no top-level directory", code != 0 and "exactly one top-level directory" in out and not installed(d), out)
	buf = io.BytesIO()
	with zipfile.ZipFile(buf, "w") as z:
		z.writestr("a-1/manifest.json", b"{}")
		z.writestr("b-1/x", b"x")
	route("/github.com/o/r/archive/v1.zip", buf.getvalue())
	d = runner.project()
	code, out = fetch(d, GH + "@v1")
	check("two top-level directories", code != 0 and "exactly one top-level directory" in out and not installed(d), out)
	for bad in ["a-1/../evil.txt", "/abs/evil.txt", "a-1\\evil.txt", "a-1/sub/../../x", "C:/evil.txt", "./a-1/x"]:
		buf = io.BytesIO()
		with zipfile.ZipFile(buf, "w") as z:
			for n, data in lib_files().items():
				z.writestr("a-1/" + n, data)
			z.writestr(bad, b"x")
		route("/github.com/o/r/archive/v1.zip", buf.getvalue())
		d = runner.project()
		code, out = fetch(d, GH + "@v1")
		check("refused entry %r" % bad, code != 0 and ("invalid file path" in out or "exactly one top-level" in out) and not installed(d), out)
	route("/github.com/o/r/archive/v1.zip", make_zip({"src/x.c3": b"x"}, top="a-1"))
	d = runner.project()
	code, out = fetch(d, GH + "@v1")
	check("no manifest at the root", code != 0 and "no manifest.json at its root" in out and not installed(d), out)
	route("/github.com/o/r/archive/v1.zip", make_zip({"sub/manifest.json": b"{}"}, top="a-1"))
	code, out = fetch(runner.project(), GH + "@v1")
	check("manifest not at the root", code != 0 and "no manifest.json at its root" in out, out)

	# A missing ref.
	reset()
	d = runner.project()
	code, out = fetch(d, GH + "@nope")
	check("404: error naming the url", code != 0 and "archive/nope.zip" in out and not installed(d), out)

	# --decompress=no.
	reset()
	route("/github.com/o/r/archive/v1.zip", archive)
	d = runner.project(["mylib"])
	code, out = runner.run(d, "--decompress=no", "fetch", GH + "@v1")
	check("decompress=no: zip written", code == 0 and os.path.isfile(lib_dir(d)) and zipfile.is_zipfile(lib_dir(d)), out)
	if os.path.isfile(lib_dir(d)):
		names = zipfile.ZipFile(lib_dir(d)).namelist()
		check("decompress=no: stripped layout", "manifest.json" in names and not any(n.startswith(".") or "/." in n for n in names), str(names))
	code, out = runner.run(d, "run", "app", url=False)
	check("decompress=no: loadable", code == 0 and "one=1" in out, out)

	# End to end, and restoring with project fetch.
	d = runner.project()
	fetch(d, GH + "@v1")
	code, out = runner.run(d, "run", "app", url=False)
	check("end to end: build and run", code == 0 and "one=1" in out, out)
	shutil.rmtree(os.path.join(d, "lib"))
	code, out = runner.run(d, "project", "fetch")
	check("project fetch: lists the missing", code == 0 and "mylib" in out, out)
	code, out = runner.run(d, "project", "fetch", "mylib")
	check("project fetch: restores", code == 0 and os.path.isfile(os.path.join(lib_dir(d), "manifest.json")) and "pin: " in out, out)
	d2 = runner.project(["%s:o/mylib@v1:%s" % (GH, "1" * 64)])
	code, out = runner.run(d2, "project", "fetch", "mylib")
	check("project fetch: pin mismatch", code != 0 and "content hash mismatch" in out and not installed(d2), out)

	# HEAD follows the repository.
	reset()
	route("/github.com/o/r/archive/HEAD.zip", archive)
	d = runner.project()
	fetch(d, GH)
	route("/github.com/o/r/archive/HEAD.zip", make_zip(lib_files(extra={"src/more.c3": b"module more;\n"}), top="r-2.0"))
	shutil.rmtree(os.path.join(d, "lib"))
	code, out = runner.run(d, "project", "fetch", "mylib")
	check("HEAD: project fetch follows the repository", code == 0 and os.path.isfile(os.path.join(lib_dir(d), "src", "more.c3")), out)

	# A fetch replaces the dependency with the same name.
	reset()
	route("/github.com/o/r/archive/v1.zip", archive)
	route("/github.com/o/r/archive/v2.zip", archive)
	d = runner.project()
	fetch(d, GH + "@v1")
	fetch(d, GH + "@v2")
	check("fetch replaces the entry of that name", runner.dependencies(d) == ["%s:o/mylib@v2:%s" % (GH, archive_hash)], str(runner.dependencies(d)))

	# A git+https dependency in the manifest of an installed library.
	reset()
	route("/github.com/o/t/archive/v1.zip", make_zip(lib_files("top", dependencies=["git+https://codeberg.org/o/q:o/dep@v1"]), top="t-1"))
	route("/codeberg.org/o/q/archive/v1.zip", make_zip(lib_files("dep"), top="q-1"))
	d = runner.project(["git+https://github.com/o/t:o/top@v1"])
	code, out = runner.run(d, "project", "fetch", "top")
	check("transitive: top fetched", code == 0 and os.path.isdir(os.path.join(d, "lib", "top.c3l")), out)
	code, out = runner.run(d, "project", "fetch")
	check("transitive: dependency missing", "dep" in out, out)
	code, out = runner.run(d, "project", "fetch", "dep")
	check("transitive: dep fetched", code == 0 and os.path.isdir(os.path.join(d, "lib", "dep.c3l")) and "/codeberg.org/o/q/archive/v1.zip" in Handler.requests, out)

	# Registry paths are parsed as before, also with a port in the url.
	d = runner.project()
	code, out = fetch(d, "ns/name:" + "a" * 64)
	check("registry path unchanged", code != 0 and "a checksum requires a version" in out, out)
	d = runner.project(["https://reg.example:8080:ns/name@1.0"])
	code, out = runner.run(d, "project", "fetch")
	check("registry url with a port", code == 0 and "name" in out and "invalid" not in out, out)
	code, out = fetch(d, "ftp://reg.example:ns/name@1.0")
	check("registry url scheme unchanged", code != 0 and "must start with http:// or https://" in out, out)

	shutil.rmtree(root, ignore_errors=True)
	server.shutdown()
	print("\n%d checks, %d failed" % (count, len(failures)))
	return 1 if failures else 0


if __name__ == "__main__":
	sys.exit(main())
