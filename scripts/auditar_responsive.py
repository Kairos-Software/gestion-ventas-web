"""Auditoría visual automatizada de las pantallas internas de Kai-Cart.

Inicia un servidor local, autentica una sesión temporal con un superusuario
existente y visita cada vista operativa en los tamaños definidos en VIEWPORTS.
No crea datos de negocio y elimina la sesión de prueba al terminar.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sistema.settings")

import django

django.setup()

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.test import Client
from django.urls import NoReverseMatch, reverse
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


HOST = "127.0.0.1"
PORT = 8765
BASE_URL = f"http://{HOST}:{PORT}"

VIEWPORTS = {
    "monitor_antiguo_800x600": (800, 600),
    "monitor_bajo_1024x600": (1024, 600),
    "telefono": (360, 800),
    "tablet_vertical": (768, 1024),
    "monitor_4_3": (1024, 768),
    "notebook": (1366, 768),
    "monitor_full_hd": (1920, 1080),
    "tv_qhd": (2560, 1440),
}

STATIC_ROUTES = [
    ("inicio", "core:home"),
    ("estadisticas_resumen", "core:estadisticas"),
    ("estadisticas_ventas", "core:estadisticas_ventas"),
    ("estadisticas_compras", "core:estadisticas_compras"),
    ("estadisticas_productos", "core:estadisticas_productos"),
    ("estadisticas_clientes", "core:estadisticas_clientes"),
    ("estadisticas_caja", "core:estadisticas_caja"),
    ("usuarios", "core:gestion_usuarios"),
    ("clientes", "core:gestion_clientes"),
    ("perfil", "core:mi_perfil"),
    ("configuracion", "core:configuracion"),
    ("catalogo_editor_interno", "core:catalogo_online"),
    ("manual", "core:manual"),
    ("notas", "core:notas"),
    ("venta_nueva", "ventas:nueva_venta"),
    ("ventas_historial", "ventas:historial_ventas"),
    ("devoluciones_historial", "ventas:historial_devoluciones"),
    ("balanza", "ventas:balanza"),
    ("productos", "productos:gestion_productos"),
    ("proveedores", "productos:gestion_proveedores"),
    ("stock", "productos:stock"),
    ("paquetes", "productos:gestion_paquetes"),
    ("ofertas", "productos:gestion_ofertas"),
    ("compra_nueva", "compras:nueva_compra"),
    ("compras_historial", "compras:historial_compras"),
    ("inventario", "compras:inventario"),
    ("caja_grande", "caja:caja_grande"),
    ("caja_diaria", "caja:caja_diaria"),
    ("turnos_historial", "caja:historial_turnos"),
    ("caja_historial_diario", "caja:historial_diario"),
    ("gastos", "caja:gastos"),
    ("transacciones", "caja:transacciones_listar_page"),
    ("deudas", "caja:deudas"),
    ("cuentas_cobrar", "caja:cuentas_cobrar"),
    ("cheques", "caja:cheques"),
    ("recargos", "caja:recargos"),
    ("presupuesto_nuevo", "presupuestos:nuevo"),
    ("presupuestos_historial", "presupuestos:historial"),
    ("pedidos_historial", "catalogo:pedidos_historial"),
]


def first_pk(app_label: str, model_name: str) -> int | None:
    model = apps.get_model(app_label, model_name)
    return model.objects.order_by("pk").values_list("pk", flat=True).first()


def build_routes(user_pk: int) -> list[tuple[str, str]]:
    routes: list[tuple[str, str]] = []
    for label, url_name in STATIC_ROUTES:
        try:
            routes.append((label, reverse(url_name)))
        except NoReverseMatch as exc:
            print(f"OMITIDA {label}: {exc}")

    permission_user_pk = (
        get_user_model().objects.filter(is_active=True, is_superuser=False)
        .order_by("pk")
        .values_list("pk", flat=True)
        .first()
    )
    dynamic = [
        ("usuario_detalle", "core:detalle_usuario", user_pk),
        ("usuario_permisos", "core:gestion_permisos", permission_user_pk),
        ("cliente_detalle", "core:cliente_detalle", first_pk("core", "Cliente")),
        ("cliente_estadisticas", "core:estadisticas_cliente_perfil", first_pk("core", "Cliente")),
        ("venta_detalle", "ventas:detalle_venta", first_pk("ventas", "Venta")),
        ("compra_detalle", "compras:detalle_compra", first_pk("compras", "Compra")),
    ]
    for label, url_name, pk in dynamic:
        if pk is not None:
            routes.append((label, reverse(url_name, args=[pk])))
        else:
            print(f"OMITIDA {label}: no hay datos para renderizarla")
    return routes


def wait_for_server(timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((HOST, PORT), timeout=0.25):
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError("El servidor de auditoría no respondió a tiempo")


AUDIT_JS = """
() => {
    const root = document.documentElement;
    const body = document.body;
    const viewportWidth = window.innerWidth;
    const overflow = Math.max(root.scrollWidth, body.scrollWidth) - viewportWidth;
    const visible = el => {
        const style = getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden' &&
               Number(style.opacity) !== 0 && rect.width > 0 && rect.height > 0;
    };
    const hasScrollParent = el => {
        let parent = el.parentElement;
        while (parent && parent !== body) {
            const style = getComputedStyle(parent);
            if (/auto|scroll/.test(style.overflowX) && parent.scrollWidth > parent.clientWidth + 1) {
                return true;
            }
            parent = parent.parentElement;
        }
        return false;
    };
    const escaped = [...document.querySelectorAll('.main-container *')]
        .filter(visible)
        .filter(el => {
            const r = el.getBoundingClientRect();
            return (r.right > viewportWidth + 2 || r.left < -2) && !hasScrollParent(el);
        })
        .slice(0, 8)
        .map(el => {
            const r = el.getBoundingClientRect();
            return `${el.tagName.toLowerCase()}.${String(el.className).replace(/\\s+/g, '.').slice(0, 70)}` +
                   `[${Math.round(r.width)}x${Math.round(r.height)}] "${(el.textContent || '').trim().slice(0, 45)}"`;
        });
    const clipped = [...document.querySelectorAll('.main-container h1, .main-container h2, .main-container h3, .main-container button, .main-container label')]
        .filter(visible)
        .filter(el => {
            const style = getComputedStyle(el);
            return (el.scrollWidth > el.clientWidth + 2 || el.scrollHeight > el.clientHeight + 2) &&
                   /hidden|clip/.test(style.overflow + style.overflowX + style.overflowY);
        })
        .slice(0, 8)
        .map(el => {
            const r = el.getBoundingClientRect();
            return `${el.tagName.toLowerCase()}.${String(el.className).replace(/\\s+/g, '.').slice(0, 70)}` +
                   `[${Math.round(r.width)}x${Math.round(r.height)}; scroll ${el.scrollWidth}x${el.scrollHeight}] ` +
                   `"${(el.textContent || '').trim().slice(0, 45)}"`;
        });
    const smallTargets = [...document.querySelectorAll('button, a.btn, [role="button"], input, select, textarea')]
        .filter(visible)
        .filter(el => !el.disabled && el.getAttribute('type') !== 'hidden')
        .filter(el => {
            if (!/checkbox|radio/.test(el.getAttribute('type') || '')) return true;
            const label = el.closest('label');
            if (!label) return true;
            const r = label.getBoundingClientRect();
            return r.width < 40 || r.height < 40;
        })
        .filter(el => {
            const r = el.getBoundingClientRect();
            return r.width < 40 || r.height < 40;
        })
        .slice(0, 8)
        .map(el => {
            const r = el.getBoundingClientRect();
            return `${el.tagName.toLowerCase()}.${String(el.className).replace(/\\s+/g, '.').slice(0, 70)}(${Math.round(r.width)}x${Math.round(r.height)})`;
        });
    return { overflow: Math.round(overflow), escaped, clipped, smallTargets };
}
"""


def main() -> int:
    user = get_user_model().objects.filter(is_active=True, is_superuser=True).order_by("pk").first()
    if user is None:
        print("No hay un superusuario activo para abrir las pantallas internas.", file=sys.stderr)
        return 2

    client = Client()
    client.force_login(user)
    cookie_name = settings.SESSION_COOKIE_NAME
    session_key = client.cookies[cookie_name].value
    routes = build_routes(user.pk)
    env = os.environ.copy()
    env["DEBUG"] = "True"
    env["ALLOWED_HOSTS"] = f"{HOST},localhost"
    server = subprocess.Popen(
        [sys.executable, "manage.py", "runserver", f"{HOST}:{PORT}", "--noreload"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    failures: list[str] = []
    warnings: list[str] = []
    visited = 0
    try:
        wait_for_server()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            for viewport_name, (width, height) in VIEWPORTS.items():
                context = browser.new_context(
                    viewport={"width": width, "height": height},
                    has_touch=width <= 768,
                    is_mobile=width < 768,
                )
                context.add_cookies([
                    {
                        "name": cookie_name,
                        "value": session_key,
                        "url": BASE_URL,
                        "httpOnly": True,
                        "sameSite": "Lax",
                    }
                ])
                page = context.new_page()
                for label, path in routes:
                    key = f"{viewport_name}/{label}"
                    try:
                        response = page.goto(
                            BASE_URL + path,
                            wait_until="domcontentloaded",
                            timeout=20_000,
                        )
                        page.wait_for_timeout(120)
                    except PlaywrightTimeoutError:
                        failures.append(f"{key}: timeout al cargar")
                        continue
                    visited += 1
                    if response is None or response.status >= 400:
                        status = "sin respuesta" if response is None else response.status
                        failures.append(f"{key}: HTTP {status}")
                        continue
                    result = page.evaluate(AUDIT_JS)
                    if result["overflow"] > 2:
                        failures.append(f"{key}: documento excede {result['overflow']}px")
                    if result["escaped"]:
                        failures.append(f"{key}: contenido fuera del viewport: {', '.join(result['escaped'])}")
                    if result["clipped"]:
                        warnings.append(f"{key}: texto posiblemente cortado: {', '.join(result['clipped'])}")
                    if width <= 768 and result["smallTargets"]:
                        warnings.append(f"{key}: controles táctiles chicos: {', '.join(result['smallTargets'])}")
                context.close()
            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
        Session.objects.filter(session_key=session_key).delete()

    print(f"Pantallas/tamaños visitados: {visited}")
    print(f"Fallos: {len(failures)}")
    for issue in failures:
        print(f"  ERROR {issue}")
    print(f"Avisos: {len(warnings)}")
    for issue in warnings:
        print(f"  AVISO {issue}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
