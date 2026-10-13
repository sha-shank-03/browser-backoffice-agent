"""Future current-semantics collector using accepted U1 authority and routes."""
from queue import Queue
import subprocess
import sys
from threading import Thread
from urllib.parse import urlparse

from backoffice.browser import PortalProcess,ROOT
from backoffice.domain import digest
from industry_backoffice.browser import V2Browser
from industry_backoffice.protocol import Halt,ModelConfig
from .lease import require_lease

SELECTOR="input:not([type=hidden]),select,button,a,summary"
EXTRACTOR="""els => els.map((el,index) => {
 const labelNode=el.labels?.[0];
 const visible=!!el.getClientRects().length && getComputedStyle(el).visibility!=='hidden';
 const role=el.tagName==='SELECT'?'combobox':el.tagName==='INPUT'?'textbox':el.tagName==='A'?'link':'button';
 const caption=labelNode?.querySelector('span');
 return {index,visible,enabled:!el.disabled,role,label:el.getAttribute('aria-label')||caption?.textContent?.trim()||labelNode?.innerText?.trim()||el.innerText.trim(),
  value:el.value||'',options:el.tagName==='SELECT'?Array.from(el.options).map(o=>({label:o.text,value:o.value})):[],
  description:el.getAttribute('aria-description')||'',context:el.closest('fieldset')?.querySelector('legend')?.textContent?.trim()||'',required:!!el.required};
}).filter(e=>e.visible&&e.enabled)"""


class EvaluationPortal(PortalProcess):
    def __enter__(self):
        require_lease()
        self.stderr_handle=(self.database.parent/"portal-eval-stderr.log").open("a",encoding="utf-8")
        self.process=subprocess.Popen([sys.executable,"-m","fresh_eval.fixture","--db",str(self.database.resolve())],cwd=ROOT,
                                      stdout=subprocess.PIPE,stderr=self.stderr_handle,text=True)
        lines=Queue()
        Thread(target=lambda:lines.put(self.process.stdout.readline()),daemon=True).start()
        try:
            self.origin=lines.get(timeout=10).strip()
            ModelConfig("local_double","fixture/local-double-v1",self.origin+"/v1/chat/completions",max_output_tokens=128).validate()
            return self
        except Exception:
            self.__exit__(None,None,None)
            raise Halt("evaluation_portal_startup") from None


class EvaluationBrowser(V2Browser):
    def __enter__(self):
        require_lease()
        return super().__enter__()

    def _controls(self):
        return self.page.locator(SELECTOR).evaluate_all(EXTRACTOR)

    def _route(self,route,request):
        self.store.data["evaluation_browser_requests"]+=1
        path=urlparse(request.url).path
        allowed={"/login","/vendors","/vendors/new","/vendors/validation","/vendors/review","/vendors/detail","/session/open","/vendors/draft","/vendors/ack","/vendors/commit"}
        self.store.save("evaluation_http_request",{"method":request.method if request.method in {"GET","POST"} else "OTHER",
                                               "path":path if path in allowed else "outside_allowlist"})
        return super()._route(route,request)

    def resolve(self,ref):
        current=digest({"url":self.page.url,"controls":self._controls()})
        if ref not in self.refs or current!=self.signature:raise Halt("stale_observation")
        item=self.refs[ref]
        signature=lambda c:(c["role"],c["label"],c["description"],c["context"])
        if sum(signature(c)==signature(item) for c in self.refs.values())!=1:raise Halt("ambiguous_current_control")
        return self.page.locator(SELECTOR).nth(item["index"]),item

    def interact(self,decision,request):
        if decision.tool=="click":
            locator,_=self.resolve(decision.arguments["ref"])
            if locator.evaluate("el=>el.tagName")=="SUMMARY":
                locator.click()
                return
        return super().interact(decision,request)

    def __exit__(self,*args):
        # Fresh evaluation never resumes a browser profile and does not export cookies/storage.
        failed=False
        if hasattr(self,"context"):
            try:self.context.close()
            except Exception:failed=True
        for resource in reversed(self.resources):
            try:resource.stop() if hasattr(resource,"stop") else resource.close()
            except Exception:failed=True
        self.resources=[]
        if failed:self.store.save("evaluation_cleanup_unknown",{"code":"owned_browser_close_failed"})
