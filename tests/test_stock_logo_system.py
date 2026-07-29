"""Browser-contract tests for the dependency-free stock logo adapter."""
from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "stock-logos.js"
SITE = ROOT / "site" / "stock-logos.js"
HAS_NODE = shutil.which("node") is not None
needs_node = pytest.mark.skipif(not HAS_NODE, reason="node not on PATH")


def _run(body: str, *, token: str | None = "publishable test token") -> dict:
    setup = ""
    if token is not None:
        setup = "globalThis.MMX_LOGO_DEV_TOKEN = %s;" % json.dumps(token)
    script = textwrap.dedent(
        """
        %(setup)s
        var Logo = require(%(module)s);
        function OUT(value) { process.stdout.write(JSON.stringify(value)); }
        %(body)s
        """
    ) % {"setup": setup, "module": json.dumps(str(TEMPLATE)), "body": body}
    result = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, (
        f"node failed:\nSTDERR:\n{result.stderr}\nSTDOUT:\n{result.stdout}"
    )
    return json.loads(result.stdout)


def test_template_and_site_assets_are_byte_identical():
    assert TEMPLATE.read_bytes() == SITE.read_bytes()


def test_no_embedded_credentials_or_bulk_download_path():
    source = TEMPLATE.read_text(encoding="utf-8")
    assert "MMX_LOGO_DEV_TOKEN" in source
    assert "Logo.dev" in source
    assert "fetch(" not in source
    assert "XMLHttpRequest" not in source
    assert "localStorage" not in source
    assert "indexedDB" not in source
    assert "download" not in source.lower()
    assert not any(marker in source for marker in ("pk_live_", "sk_live_", "secret_key"))


@needs_node
def test_us_canada_hk_and_china_ticker_normalization():
    out = _run(
        """
        OUT({
          us: Logo.normalizeTicker(' nasdaq:AAPL ', 'US'),
          usClass: Logo.normalizeTicker('BRK.B', 'United States'),
          ca: Logo.normalizeTicker('SHOP.TSE', 'Canada'),
          caBare: Logo.normalizeTicker('RY', 'TSX'),
          hk: Logo.normalizeTicker('700', 'Hong Kong'),
          sh: Logo.normalizeTicker('600519.SH', 'China'),
          sz: Logo.normalizeTicker('000001', 'CN'),
          bj: Logo.normalizeTicker('430047', 'CN')
        });
        """
    )
    assert out == {
        "us": "AAPL",
        "usClass": "BRK.B",
        "ca": "SHOP.TO",
        "caBare": "RY.TO",
        "hk": "0700.HK",
        "sh": "600519.SS",
        "sz": "000001.SZ",
        "bj": "430047.BJ",
    }


@needs_node
def test_international_suffixes_and_ambiguous_company_name_fallback():
    out = _run(
        """
        OUT({
          uk: Logo.sourceFor({t:'SHEL.LN', n:'Shell plc', _mk:'Intl'}),
          japan: Logo.sourceFor({ticker:'7203.JP', name:'Toyota', market:'global'}),
          ambiguous: Logo.sourceFor({
            ticker:'NESTLE', name:'Nestlé S.A. / Global', market:'International'
          }),
          beijing: Logo.sourceFor({
            ticker:'430047.BJ', name:'诺思兰德', market:'China'
          })
        });
        """
    )
    assert out["uk"]["kind"] == "ticker" and out["uk"]["value"] == "SHEL.L"
    assert out["japan"]["kind"] == "ticker" and out["japan"]["value"] == "7203.T"
    assert out["ambiguous"]["kind"] == "name"
    assert out["ambiguous"]["value"] == "Nestlé S.A. / Global"
    assert out["beijing"]["kind"] == "name"


@needs_node
def test_urls_encode_path_and_query_values_and_select_theme():
    out = _run(
        """
        var light = Logo.buildUrl({
          ticker:'NESTLE', name:"Nestlé S.A. / R&D", market:'Intl'
        }, 'light');
        var dark = Logo.buildUrl({ticker:'0700.HK', market:'HK'}, 'dark');
        OUT({light:light, dark:dark});
        """,
        token="publishable token & tenant=alpha",
    )
    assert out["light"].startswith(
        "https://img.logo.dev/name/Nestl%C3%A9%20S.A.%20%2F%20R%26D?"
    )
    assert "token=publishable+token+%26+tenant%3Dalpha" in out["light"]
    assert "theme=light" in out["light"]
    assert "/ticker/0700.HK?" in out["dark"]
    assert "theme=dark" in out["dark"]


@needs_node
def test_missing_token_is_a_clean_monogram_only_mode():
    out = _run(
        """
        OUT({
          url: Logo.buildUrl({ticker:'AAPL', name:'Apple', market:'US'}, 'dark'),
          mark: Logo.monogramFor({ticker:'AAPL', name:'Apple', market:'US'}),
          flag: Logo.flagFor({ticker:'AAPL', market:'US'})
        });
        """,
        token=None,
    )
    assert out == {"url": "", "mark": "AP", "flag": "🇺🇸"}


@needs_node
def test_country_flags_cover_search_markets_and_international_rows():
    out = _run(
        """
        OUT({
          us: Logo.flagFor({t:'AAPL', _mk:'US'}),
          ca: Logo.flagFor({t:'SHOP.TO', _mk:'Canada'}),
          hk: Logo.flagFor({t:'0700.HK', _mk:'HK'}),
          cn: Logo.flagFor({t:'600519.SS', _mk:'China'}),
          intl: Logo.flagFor({t:'SHEL.L', _mk:'Intl'}),
          explicit: Logo.flagFor({t:'BHP.AX', _mk:'Intl', _fl:'🏴'})
        });
        """
    )
    assert out == {
        "us": "🇺🇸",
        "ca": "🇨🇦",
        "hk": "🇭🇰",
        "cn": "🇨🇳",
        "intl": "🇬🇧",
        "explicit": "🏴",
    }


@needs_node
def test_enhance_supports_the_nav_search_data_attribute_contract():
    script = textwrap.dedent(
        """
        class Element {
          constructor(tag) {
            this.tagName=tag; this.children=[]; this.firstChild=null; this.attributes={};
            this.dataset={}; this.isConnected=true;
            this.style={setProperty:function(k,v){this[k]=v;}};
          }
          setAttribute(k,v){this.attributes[k]=String(v);}
          getAttribute(k){return this.attributes[k]===undefined?null:this.attributes[k];}
          appendChild(n){this.children.push(n);this.firstChild=this.children[0]||null;return n;}
          removeChild(n){this.children.splice(this.children.indexOf(n),1);this.firstChild=this.children[0]||null;}
        }
        var html=new Element('html'), head=new Element('head');
        globalThis.document={
          documentElement:html,head:head,createElement:function(tag){var n=new Element(tag);n.ownerDocument=this;return n;},
          getElementById:function(){return null;},addEventListener:function(){}
        };
        var slot=new Element('span'); slot.ownerDocument=document;
        slot.dataset={ticker:'SHEL.L',company:'Shell plc',market:'Intl',flag:'🇬🇧'};
        slot.setAttribute('data-logo-size','28');
        var scope={querySelectorAll:function(selector){return selector==='[data-stock-logo]'?[slot]:[];}};
        var Logo=require(%(module)s);
        var made=Logo.enhance(scope);
        var logo=slot.children[0];
        process.stdout.write(JSON.stringify({
          count:made.length,ticker:logo.getAttribute('data-logo-ticker'),
          aria:logo.getAttribute('aria-label'),size:logo.style['--mmx-logo-size'],
          mark:logo.children[1].textContent,flag:logo.children[2].textContent,
          hasSrc:logo.children[0].getAttribute('src')
        }));
        """
    ) % {"module": json.dumps(str(TEMPLATE))}
    result = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "count": 1,
        "ticker": "SHEL.L",
        "aria": "Shell plc logo",
        "size": "28px",
        "mark": "SP",
        "flag": "🇬🇧",
        "hasSrc": None,
    }


@needs_node
def test_render_is_lazy_accessible_theme_refreshable_and_failure_safe():
    script = textwrap.dedent(
        """
        class Element {
          constructor(tag) {
            this.tagName = tag.toUpperCase(); this.children = []; this.attributes = {};
            this.style = {display:'', setProperty:function(k,v){this[k]=v;}};
            this.isConnected = true; this.firstChild = null; this.dataset = {};
          }
          setAttribute(k,v) { this.attributes[k] = String(v); }
          getAttribute(k) { return this.attributes[k] === undefined ? null : this.attributes[k]; }
          removeAttribute(k) { delete this.attributes[k]; }
          appendChild(n) { this.children.push(n); this.firstChild = this.children[0] || null; return n; }
          removeChild(n) { this.children.splice(this.children.indexOf(n),1); this.firstChild=this.children[0]||null; }
          getBoundingClientRect() { return {width:30,height:30,top:0,left:0,right:30,bottom:30}; }
        }
        var html = new Element('html');
        html.setAttribute('data-theme', 'light');
        var head = new Element('head');
        var listeners = {};
        globalThis.document = {
          documentElement: html, head: head, visibilityState: 'visible',
          createElement: function(tag){ return new Element(tag); },
          getElementById: function(){ return null; },
          addEventListener: function(name, fn){ listeners[name] = fn; }
        };
        var observed = null, ioCallback = null;
        globalThis.IntersectionObserver = function(cb) {
          ioCallback = cb;
          this.observe = function(node){ observed = node; };
          this.unobserve = function(){};
        };
        globalThis.MMX_LOGO_DEV_TOKEN = 'visible-only';
        var Logo = require(%(module)s);
        var logo = Logo.create({t:'AAPL', n:'Apple Inc.', _mk:'US', _fl:'🇺🇸'});
        var image = logo.children[0], fallback = logo.children[1], flag = logo.children[2];
        var before = image.getAttribute('src');
        ioCallback([{target:observed,isIntersecting:true,intersectionRatio:1}]);
        var first = image.getAttribute('src');
        image.onerror();
        var failed = {
          src:image.getAttribute('src'), state:logo.getAttribute('data-logo-state'),
          imageDisplay:image.style.display, fallbackDisplay:fallback.style.display
        };
        html.setAttribute('data-theme', 'dark');
        Logo.refreshTheme();
        var dark = image.getAttribute('src');
        var attr = Logo.createAttribution(document);
        process.stdout.write(JSON.stringify({
          before:before, first:first, failed:failed, dark:dark,
          role:logo.getAttribute('role'), aria:logo.getAttribute('aria-label'),
          alt:image.alt, mark:fallback.textContent, flag:flag.textContent,
          flagHidden:flag.getAttribute('aria-hidden'),
          attribution:{text:attr.textContent,href:attr.href,rel:attr.rel}
        }));
        """
    ) % {"module": json.dumps(str(TEMPLATE))}
    result = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["before"] is None
    assert "theme=light" in out["first"]
    assert out["failed"] == {
        "src": None,
        "state": "fallback",
        "imageDisplay": "none",
        "fallbackDisplay": "grid",
    }
    assert "theme=dark" in out["dark"]
    assert out["role"] == "img"
    assert out["aria"] == out["alt"] == "Apple Inc. logo"
    assert out["mark"] == "AI"
    assert out["flag"] == "🇺🇸" and out["flagHidden"] == "true"
    assert out["attribution"] == {
        "text": "Logos provided by Logo.dev",
        "href": "https://www.logo.dev/",
        "rel": "noopener noreferrer",
    }
