import httpx

from getnet_multi_agent.rag.crawler import PAUSE_SECONDS, Crawler, SourceSite

SITE = SourceSite("https://a.test/", "a.test", "", "brazil_site", ("https://a.test/must/",))
GLOBAL = SourceSite("https://b.test/en", "b.test", "/en", "global_site", ())


def html(body):
    return f"<html><title>t</title><body>{body}</body></html>"


def make_crawler(tmp_path, routes, **kwargs):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        result = routes.get(str(request.url), (404, "text/html", "nf"))
        status, ctype, text = result[:3]
        if status in (301, 302):
            return httpx.Response(status, headers={"location": text})
        return httpx.Response(status, headers={"content-type": ctype}, text=text)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    sleeps = []
    crawler = Crawler(tmp_path / "cache", kwargs.pop("max_pages", 80), client=client, sleep=sleeps.append, **kwargs)
    return crawler, calls, sleeps


BASE_ROUTES = {
    "https://a.test/": (200, "text/html", html('<a href="/one">1</a><a href="/two.pdf">p</a><a href="https://other.test/x">o</a><a href="/doc">d</a><a href="/dup">d</a>')),
    "https://a.test/must/": (200, "text/html; charset=utf-8", html("must")),
    "https://a.test/one": (200, "text/html", html("one")),
    "https://a.test/doc": (200, "application/pdf", ""),
    "https://a.test/dup": (200, "text/html", html("one")),
}


def test_R19_one_level_deep_same_host_only(tmp_path):
    routes = {**BASE_ROUTES, "https://a.test/one": (200, "text/html", html('one <a href="/deep">d</a>'))}
    crawler, calls, _ = make_crawler(tmp_path, routes)
    crawler.crawl((SITE,))
    assert "https://a.test/deep" not in calls and not any("other.test" in c for c in calls)


def test_R19_global_source_keeps_only_en_paths(tmp_path):
    routes = {"https://b.test/en": (200, "text/html", html('<a href="/en/x">x</a><a href="/es/y">y</a><a href="/english">z</a>')), "https://b.test/en/x": (200, "text/html", html("x"))}
    crawler, calls, _ = make_crawler(tmp_path, routes)
    result = crawler.crawl((GLOBAL,))
    assert {p.final_url for p in result.pages} == {"https://b.test/en", "https://b.test/en/x"}
    assert not any("/es/" in c or "/english" in c for c in calls)


def test_R20_required_pages_come_before_the_cap(tmp_path):
    crawler, _, _ = make_crawler(tmp_path, BASE_ROUTES, max_pages=2)
    result = crawler.crawl((SITE,))
    assert [p.final_url for p in result.pages] == ["https://a.test/", "https://a.test/must/"]


def test_R21_dedupes_by_hash_and_keeps_only_html_200(tmp_path):
    crawler, _, _ = make_crawler(tmp_path, BASE_ROUTES)
    urls = {p.final_url for p in crawler.crawl((SITE,)).pages}
    assert urls == {"https://a.test/", "https://a.test/must/", "https://a.test/one"}


def test_R21_dedupes_by_final_url_and_drops_off_host_redirects(tmp_path):
    routes = {
        "https://a.test/": (200, "text/html", html('<a href="/r1">1</a><a href="/r2">2</a>')),
        "https://a.test/must/": (200, "text/html", html("must")),
        "https://a.test/r1": (302, "", "https://a.test/must/"),
        "https://a.test/r2": (302, "", "https://other.test/x"),
        "https://other.test/x": (200, "text/html", html("other")),
    }
    crawler, _, _ = make_crawler(tmp_path, routes)
    urls = [p.final_url for p in crawler.crawl((SITE,)).pages]
    assert urls == ["https://a.test/", "https://a.test/must/"]


def test_R22_pauses_two_seconds_between_network_requests(tmp_path):
    crawler, calls, sleeps = make_crawler(tmp_path, BASE_ROUTES)
    crawler.crawl((SITE,))
    assert PAUSE_SECONDS == 2.0 and len(sleeps) == len(calls) - 1


def test_R23_cached_urls_are_not_refetched_unless_refresh(tmp_path):
    crawler, calls, _ = make_crawler(tmp_path, BASE_ROUTES)
    crawler.crawl((SITE,))
    assert calls
    second, second_calls, _ = make_crawler(tmp_path, BASE_ROUTES)
    assert len(second.crawl((SITE,)).pages) == 3 and second_calls == []
    third, third_calls, _ = make_crawler(tmp_path, BASE_ROUTES, refresh=True)
    third.crawl((SITE,))
    assert third_calls


def test_R24_stops_host_at_first_403_or_429_but_continues_other_host(tmp_path):
    routes = {
        **BASE_ROUTES,
        "https://a.test/must/": (429, "text/html", ""),
        "https://b.test/en": (200, "text/html", html("en")),
    }
    crawler, calls, _ = make_crawler(tmp_path, routes)
    result = crawler.crawl((SITE, GLOBAL))
    assert result.stopped_hosts == ["a.test"]
    assert "https://a.test/one" not in calls
    assert {p.final_url for p in result.pages} == {"https://a.test/", "https://b.test/en"}


def test_R28_network_error_on_a_source_does_not_raise(tmp_path):
    def handler(request):
        raise httpx.ConnectError("down")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert Crawler(tmp_path / "c", 80, client=client, sleep=lambda _: None).crawl((SITE,)).pages == []
