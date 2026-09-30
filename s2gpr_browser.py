from playwright.async_api import async_playwright
import asyncio

S2GPR_LOGIN_URL = (
    "https://s2gpr.sefaz.ce.gov.br/"
    "cotacao-web/padrao-web/paginas/seguranca/login.seam"
)


class S2GPRBrowser:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.connected = False
        self.status = "disconnected"

    async def start(self):
        if self.browser:
            return

        self.playwright = await async_playwright().start()

        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        self.context = await self.browser.new_context(
    viewport={"width": 1440, "height": 900},
    ignore_https_errors=True,
)

        self.page = await self.context.new_page()

    async def connect(self, usuario: str, senha: str):
        await self.start()

        self.status = "connecting"

        await self.page.goto(
            S2GPR_LOGIN_URL,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        html = (await self.page.content()).lower()

        if "captcha" in html or "recaptcha" in html:
            self.status = "human_action_required"
            return {
                "connected": False,
                "status": "human_action_required",
                "reason": "captcha",
            }

        try:
            usuario_input = self.page.locator(
                'input[type="text"], input[name*="usuario" i], input[id*="usuario" i]'
            ).first

            senha_input = self.page.locator(
                'input[type="password"]'
            ).first

            await usuario_input.fill(usuario)
            await senha_input.fill(senha)

            login_button = self.page.locator(
                'button:has-text("Entrar"), '
                'input[type="submit"], '
                'button[type="submit"]'
            ).first

            await login_button.click()

            await self.page.wait_for_timeout(3000)

            current_url = self.page.url
            page_text = (await self.page.inner_text("body")).lower()

            if "captcha" in page_text or "mfa" in page_text:
                self.status = "human_action_required"

                return {
                    "connected": False,
                    "status": "human_action_required",
                    "reason": "captcha_or_mfa",
                }

            if "senha" in page_text and "usuário" in page_text:
                self.connected = False
                self.status = "authentication_failed"

                return {
                    "connected": False,
                    "status": "authentication_failed",
                }

            self.connected = True
            self.status = "authenticated"

            return {
                "connected": True,
                "status": "authenticated",
                "url": current_url,
            }

        except Exception as exc:
            self.connected = False
            self.status = "error"

            return {
                "connected": False,
                "status": "error",
                "message": str(exc),
            }

    async def session_status(self):
        return {
            "connected": self.connected,
            "status": self.status,
            "url": self.page.url if self.page else None,
        }

    async def disconnect(self):
        if self.context:
            await self.context.close()

        if self.browser:
            await self.browser.close()

        if self.playwright:
            await self.playwright.stop()

        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.connected = False
        self.status = "disconnected"

        return {
            "connected": False,
            "status": "disconnected",
        }


s2gpr_browser = S2GPRBrowser()
