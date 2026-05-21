from realtorfarm.blob import load_env_value, parse_store_id_from_token, upload_file_to_vercel_blob


def test_load_env_value_supports_equals_and_space_formats(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("BLOB_READ_WRITE_TOKEN token-from-space\nOTHER=value\nGITHUB_TOKEN=token-from-equals\n", encoding="utf-8")
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    assert load_env_value("BLOB_READ_WRITE_TOKEN", env_paths=(str(env),)) == "token-from-space"
    assert load_env_value("GITHUB_TOKEN", env_paths=(str(env),)) == "token-from-equals"


def test_parse_store_id_from_read_write_token():
    assert parse_store_id_from_token("vercel_blob_rw_store_UqbIA72ov0PUTTqT_xxx") == "store_UqbIA72ov0PUTTqT"


def test_upload_file_to_vercel_blob_sends_private_overwrite_put(tmp_path, monkeypatch):
    output = tmp_path / "latest.json.txt"
    output.write_text('data= {"properties": []}\n', encoding="utf-8")
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"pathname":"burien/latest.json.txt","url":"https://example.invalid/blob"}'

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["headers"] = dict(request.header_items())
        captured["body"] = request.data
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = upload_file_to_vercel_blob(
        output,
        pathname="burien/latest.json.txt",
        token="vercel_blob_rw_store_UqbIA72ov0PUTTqT_secret",
    )

    assert result["pathname"] == "burien/latest.json.txt"
    assert captured["method"] == "PUT"
    assert "pathname=burien%2Flatest.json.txt" in captured["url"]
    assert captured["headers"]["X-vercel-blob-access"] == "private"
    assert captured["headers"]["X-allow-overwrite"] == "1"
    assert captured["headers"]["X-vercel-blob-store-id"] == "store_UqbIA72ov0PUTTqT"
    assert captured["body"] == output.read_bytes()
