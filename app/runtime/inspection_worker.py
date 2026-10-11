"""Disposable, process-owned browser/UIA worker. No arbitrary evaluation API."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from time import monotonic, sleep
from urllib.parse import urlsplit, urljoin


def browser_inspection(spec):
    if spec.get("browser_directory"):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = spec["browser_directory"]
    from playwright.sync_api import Error as BrowserError, sync_playwright
    server = None
    if spec["server_executable"]:
        server = subprocess.Popen([spec["server_executable"], *spec["server_arguments"]],
            cwd=spec["project_path"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, shell=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    problems, checks = [], []
    def problem(kind, detail):
        if len(problems) < 24:
            problems.append({"kind": kind, "detail": str(detail)[:300]})
    origin = urlsplit(spec["url"])
    def same_origin(url):
        other = urlsplit(url)
        return other.hostname == origin.hostname and (other.port or 80) == (origin.port or 80)
    with sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": spec["width"], "height": spec["height"]},
            service_workers="block", accept_downloads=False)
        try:
            # Routed HTTP responses otherwise appear outside the local address
            # space to Chromium, blocking Vite's same-origin development socket.
            # This disposable origin grant leaves the HTTP/WebSocket routes below
            # responsible for enforcing the exact approved host and port.
            context.grant_permissions(["local-network-access"], origin=f"{origin.scheme}://{origin.netloc}")
            def route(request):
                try:
                    if urlsplit(request.request.url).scheme == "http" and same_origin(request.request.url):
                        response = request.fetch(max_redirects=0, timeout=10000)
                        redirect = response.headers.get("location")
                        if response.status in {301, 302, 303, 307, 308} and redirect and (
                                urlsplit(urljoin(request.request.url, redirect)).scheme != "http"
                                or not same_origin(urljoin(request.request.url, redirect))):
                            problem("blocked_redirect", redirect)
                            request.abort()
                        else:
                            request.fulfill(response=response)
                    else:
                        problem("blocked_reference", request.request.url)
                        request.abort()
                except BrowserError:
                    # Startup/refused connections and slow assets are observations,
                    # not unhandled callback tracebacks mixed into the JSON receipt.
                    problem("failed_reference", request.request.url)
                    try:
                        request.abort("failed")
                    except BrowserError:
                        pass  # Navigation/context may already have closed this route.
            context.route("**/*", route)
            blocked_sockets = []
            def websocket(route):
                if same_origin(route.url) and urlsplit(route.url).scheme == "ws":
                    route.connect_to_server()
                else:
                    problem("blocked_reference", route.url)
                    # Never connect this route. Closing from the initial script's
                    # routing callback can wait on that same script's context;
                    # settle the mock socket after navigation instead.
                    if len(blocked_sockets) < 24:
                        blocked_sockets.append(route)
            context.route_web_socket("**/*", websocket)
            page = context.new_page()
            page.set_default_timeout(2000)
            page.on("dialog", lambda dialog: dialog.dismiss())
            page.on("pageerror", lambda error: problem("page_error", error))
            page.on("console", lambda message: problem("console_error", message.text) if message.type == "error" else None)
            page.on("response", lambda response: problem("http_error", f"{response.status} {response.url}") if response.status >= 400 else None)
            page.on("requestfailed", lambda request: problem("failed_reference", request.url))
            # A newly started preview may need a moment to bind; no remote readiness probes.
            deadline = monotonic() + min(10, spec["timeout_seconds"])
            while True:
                try:
                    page.goto(spec["url"], wait_until="load", timeout=10000)
                    break
                except BrowserError as error:
                    if server is None:
                        return {"passed": False, "inspection_complete": False,
                            "verification_status": "unavailable",
                            "failure_kind": "preview_navigation_failed", "preview_server_started": False,
                            "error": str(error)[:300], "recovery": {
                                "capability": "project.inspect",
                                "required_if_preview_not_running": ["server_executable", "server_arguments"],
                                "instruction": "No preview server was started by this inspection. If no server is already running, "
                                    "retry project.inspect with the installed interpreter in server_executable and the project's "
                                    "documented preview command in server_arguments, using the same host/port as url. "
                                    "This keeps the server alive throughout inspection and stops it afterward. "
                                    "shell.run stops its child processes when it returns, so starting a server there "
                                    "cannot keep it alive for a later inspection. The corrected call still requires approval."}}
                    if server.poll() is not None or monotonic() >= deadline:
                        raise
                    problems.clear()
                    sleep(0.1)
            for socket in blocked_sockets:
                socket.close(code=1000, reason="Outside the approved preview origin")
            blocked_sockets.clear()
            for step in spec["steps"]:
                action, target = step["action"], step["target"]
                check = {"action": action, "target": target, "passed": False}
                try:
                    locator = page.locator(target) if target else None
                    timeout = step.get("timeout_ms", 2000)
                    if action == "wait":
                        if locator:
                            locator.wait_for(state=step.get("state", "visible"), timeout=timeout)
                        else:
                            page.wait_for_timeout(timeout)
                    elif action == "in_view":
                        locator.scroll_into_view_if_needed(timeout=timeout)
                        page.wait_for_timeout(250)  # Observe application scroll handlers after the move.
                        box = locator.bounding_box()
                        check["bounds"] = box
                        if not box or box["width"] <= 0 or box["height"] <= 0 or not (
                                box["y"] < spec["height"] and box["y"] + box["height"] > 0 and
                                box["x"] < spec["width"] and box["x"] + box["width"] > 0):
                            raise ValueError("Target did not remain in the viewport; wait for intro/scroll-lock completion before inspecting this section.")
                    elif action == "model_loaded":
                        locator.wait_for(state="attached", timeout=timeout)
                        locator.evaluate("""(e, timeout) => new Promise((resolve, reject) => {
                            const start=performance.now();
                            const poll=()=> {
                                if(e.tagName !== 'MODEL-VIEWER') { reject(new Error('Target must be model-viewer.')); return; }
                                if(customElements.get('model-viewer') && e.loaded === true) { resolve(true); return; }
                                if(performance.now()-start >= timeout) { reject(new Error('model-viewer is undefined or its model has not loaded.')); return; }
                                setTimeout(poll,50);
                            }; poll();
                        })""", timeout)
                    elif action == "click":
                        locator.click()
                    elif action == "fill":
                        locator.fill(step["value"])
                    elif action == "visible":
                        locator.wait_for(state="visible", timeout=timeout)
                    elif action == "text":
                        if step["value"] not in locator.inner_text():
                            raise ValueError("Expected text is absent.")
                    else:
                        script = "e => ({top:e.scrollTop, height:e.scrollHeight, viewport:e.clientHeight})"
                        before = locator.evaluate(script) if locator else page.evaluate("() => document.scrollingElement.scrollTop")
                        if locator:
                            locator.hover()
                        else:
                            page.mouse.move(spec["width"] // 2, spec["height"] // 2)
                        page.mouse.wheel(0, step["amount"])
                        page.wait_for_timeout(200)
                        after = locator.evaluate(script) if locator else page.evaluate("() => document.scrollingElement.scrollTop")
                        values = {"before": before["top"] if locator else before,
                            "after": after["top"] if locator else after}
                        check["scroll"] = values
                        if values["before"] == values["after"] and step["amount"]:
                            raise ValueError("Scroll did not move; verify overflow and scroll ownership.")
                    check["passed"] = True
                except Exception as error:
                    check["error"] = str(error)[:300]
                checks.append(check)
            layout = page.evaluate("""() => {
                const e=document.scrollingElement, all=[...document.querySelectorAll('*')], scan=all.slice(0,2000);
                const brokenImages=scan.filter(x=>x.tagName==='IMG' && (!x.complete || x.naturalWidth===0)).slice(0,20).map(x=>x.getAttribute('src'));
                const missingFragments=scan.filter(x=>x.tagName==='A' && (x.getAttribute('href')||'').startsWith('#') && x.hash.length>1 && !document.getElementById(decodeURIComponent(x.hash.slice(1)))).slice(0,20).map(x=>x.hash);
                return {scrollTop:e.scrollTop, scrollHeight:e.scrollHeight, viewportHeight:e.clientHeight,
                    horizontalOverflow:e.scrollWidth>e.clientWidth+1, brokenImages, missingFragments,
                    elementsScanned:scan.length, scanTruncated:all.length>scan.length,
                    previewError:document.querySelector('vite-error-overlay')?.shadowRoot?.textContent?.slice(0,1000) || null,
                    models:scan.filter(x=>x.tagName==='MODEL-VIEWER').slice(0,12).map(x=> {
                        const r=x.getBoundingClientRect();
                        return {src:x.getAttribute('src'), defined:!!customElements.get('model-viewer'),
                            loaded:x.loaded===true, modelIsVisible:x.modelIsVisible===true,
                            width:r.width, height:r.height,
                            inViewport:r.width>0 && r.height>0 && r.top<innerHeight && r.bottom>0 && r.left<innerWidth && r.right>0};
                    })};
            }""")
            if layout["previewError"]:
                problem("preview_error", layout["previewError"])
            # Re-check requested sections at capture time: a subsequent action or
            # late intro handler may have moved an earlier target out of view.
            capture_targets = []
            for step in spec["steps"]:
                if step["action"] != "in_view":
                    continue
                try:
                    box = page.locator(step["target"]).bounding_box()
                except BrowserError:
                    box = None
                visible = bool(box and box["width"] > 0 and box["height"] > 0 and
                    box["y"] < spec["height"] and box["y"] + box["height"] > 0 and
                    box["x"] < spec["width"] and box["x"] + box["width"] > 0)
                capture_targets.append({"target": step["target"], "in_viewport": visible, "bounds": box})
                if not visible:
                    problem("capture_target_outside_viewport", step["target"])
            if layout["horizontalOverflow"]:
                problem("horizontal_overflow", "Page extends beyond the viewport.")
            for value in layout["brokenImages"]:
                problem("broken_image", value)
            for value in layout["missingFragments"]:
                problem("missing_fragment", value)
            page.screenshot(path=spec["screenshot"], full_page=False, timeout=3000)
            passed = not problems and all(item["passed"] for item in checks)
            return {"passed": passed, "verification_status": "passed" if passed else "failed", "url": page.url,
                "title": page.title()[:200], "checks": checks, "problems": problems, "layout": layout,
                "capture_targets": capture_targets,
                "screenshot_path": spec["screenshot"], "preview_pid": server.pid if server is not None else None,
                "retry_guidance": None if passed else (
                    "Inspection ran; these are failed checks, not an unavailable browser. "
                    "Correct invalid selectors or preview setup before retrying. Repeating checks does not repair project code. "
                    "For a read-only test/report request, report the observed failures and any unverified interaction or visual checks. "
                    "If source edits are authorized, fix the relevant code before retesting. Do not claim failed checks passed."),
                "scope": "Loaded local preview, specified interactions and viewport; screenshot requires visual review."}
        finally:
            context.close()
            browser.close()


def desktop_inspection(spec):
    import psutil
    from pywinauto import Application
    process = psutil.Process(spec["pid"])
    if process.create_time() != spec["target_created_at"] or Path(process.cwd()).resolve() != Path(spec["project_path"]).resolve():
        raise ValueError("Desktop process project changed.")
    app = Application(backend="uia").connect(process=spec["pid"], timeout=3)
    windows = [window for window in app.windows() if window.is_visible()]
    if len(windows) != 1:
        raise ValueError(f"Desktop inspection requires exactly one visible project window; found {len(windows)}.")
    window = windows[0]
    checks = []
    def resolve_target(name):
        if not name:
            return window
        queue, found, scanned = [(window, 0)], [], 0
        while queue and scanned < 100:
            control, depth = queue.pop(0)
            scanned += 1
            if control.element_info.automation_id == name or control.window_text() == name:
                found.append(control)
            if depth < 5:
                queue.extend((child, depth + 1) for child in control.children()[:100])
        if len(found) != 1:
            raise ValueError("Target must uniquely match an automation ID or exact accessible name in the bounded tree.")
        return found[0]
    for step in spec["steps"]:
        check = {"action": step["action"], "target": step["target"], "passed": False}
        try:
            if step["action"] in {"visible", "text"}:
                deadline = monotonic() + 2
                while True:
                    try:
                        target = resolve_target(step["target"])
                        if step["action"] == "visible" and not target.is_visible():
                            raise ValueError("Target is not visible.")
                        if step["action"] == "text" and step["value"] not in target.window_text():
                            raise ValueError("Expected text is absent.")
                        break
                    except Exception:
                        if monotonic() >= deadline:
                            raise
                        sleep(0.05)
            target = resolve_target(step["target"])
            if step["action"] == "click":
                target.invoke()  # UIA Invoke; no global mouse/keyboard input.
            elif step["action"] == "fill":
                target.set_edit_text(step["value"])
            elif step["action"] == "visible":
                if not target.is_visible():
                    raise ValueError("Target is not visible.")
            elif step["action"] == "text":
                if step["value"] not in target.window_text():
                    raise ValueError("Expected text is absent.")
            else:
                scroll = target.iface_scroll
                before = scroll.CurrentVerticalScrollPercent
                scroll.Scroll(2, 3 if step["amount"] > 0 else 0)
                after = scroll.CurrentVerticalScrollPercent
                check["scroll"] = {"before": before, "after": after}
                if before == after:
                    raise ValueError("Scroll did not move.")
            check["passed"] = True
        except Exception as error:
            check["error"] = str(error)[:300]
        checks.append(check)
    # Traverse breadth-first with a strict cap instead of unbounded descendants().
    queue, controls = [(window, 0)], []
    while queue and len(controls) < 100:
        control, depth = queue.pop(0)
        rect = control.rectangle()
        controls.append({"name": control.window_text()[:200], "automation_id": control.element_info.automation_id[:200],
            "control_type": control.element_info.control_type, "visible": control.is_visible(),
            "rectangle": [rect.left, rect.top, rect.right, rect.bottom]})
        if depth < 5:
            queue.extend((child, depth + 1) for child in control.children()[:100])
    image = capture_window(window)
    image.thumbnail((spec["width"], spec["height"]))
    image.save(spec["screenshot"])
    return {"passed": all(item["passed"] for item in checks), "pid": spec["pid"], "checks": checks,
        "controls": controls, "controls_truncated": bool(queue), "screenshot_path": spec["screenshot"],
        "scope": "Approved project window and specified UIA interactions; screenshot requires visual review."}


def capture_window(window):
    """Render only the approved HWND; never sample unrelated overlapping desktop pixels."""
    import ctypes
    from ctypes import wintypes
    from PIL import Image
    import win32gui
    left, top, right, bottom = win32gui.GetWindowRect(window.handle)
    width, height = right - left, bottom - top
    if not (0 < width <= 4096 and 0 < height <= 4096):
        raise ValueError("Window capture exceeds its bounded dimensions.")
    dc = win32gui.GetWindowDC(window.handle)
    memory = win32gui.CreateCompatibleDC(dc)
    bitmap = win32gui.CreateCompatibleBitmap(dc, width, height)
    previous = win32gui.SelectObject(memory, bitmap)
    try:
        render = ctypes.windll.user32.PrintWindow
        render.argtypes, render.restype = [wintypes.HWND, wintypes.HDC, wintypes.UINT], wintypes.BOOL
        if not render(window.handle, int(memory), 2):
            raise ValueError("The approved window could not be captured.")
        win32gui.SelectObject(memory, previous)
        class Header(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("width", wintypes.LONG), ("height", wintypes.LONG),
                ("planes", wintypes.WORD), ("bits", wintypes.WORD), ("compression", wintypes.DWORD),
                ("image_size", wintypes.DWORD), ("x_resolution", wintypes.LONG), ("y_resolution", wintypes.LONG),
                ("colors", wintypes.DWORD), ("important", wintypes.DWORD)]
        header = Header(size=ctypes.sizeof(Header), width=width, height=-height, planes=1, bits=32)
        pixels = ctypes.create_string_buffer(width * height * 4)
        read = ctypes.windll.gdi32.GetDIBits
        read.argtypes, read.restype = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
            ctypes.c_void_p, ctypes.POINTER(Header), wintypes.UINT], ctypes.c_int
        if read(int(memory), int(bitmap), 0, height, pixels, ctypes.byref(header), 0) != height:
            raise ValueError("The approved window pixels could not be read.")
        return Image.frombuffer("RGB", (width, height), pixels.raw, "raw", "BGRX", 0, 1).copy()
    finally:
        win32gui.SelectObject(memory, previous)
        win32gui.DeleteObject(bitmap)
        win32gui.DeleteDC(memory)
        win32gui.ReleaseDC(window.handle, dc)


if __name__ == "__main__":
    try:
        spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        result = browser_inspection(spec) if spec["kind"] == "browser" else desktop_inspection(spec)
        print(json.dumps(result, ensure_ascii=False))
    except ImportError:
        print("Inspection dependency unavailable. Install the verification extra and Playwright Chromium.")
        sys.exit(2)
    except Exception as error:
        print(f"Inspection failed: {type(error).__name__}: {str(error)[:500]}")
        sys.exit(1)
