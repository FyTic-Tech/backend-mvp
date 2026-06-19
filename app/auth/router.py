import os
import resend
import jwt as pyjwt
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter()

HOOK_EMAIL_TEMPLATES = {
    "signup": {
        "subject": "Confirma tu registro en FyTic",
        "action_label": "Confirmar correo",
    },
    "recovery": {
        "subject": "Restablece tu contraseña en FyTic",
        "action_label": "Restablecer contraseña",
    },
    "invite": {
        "subject": "Te invitaron a FyTic",
        "action_label": "Aceptar invitación",
    },
    "magic_link": {
        "subject": "Tu enlace de acceso a FyTic",
        "action_label": "Iniciar sesión",
    },
    "email_change_new": {
        "subject": "Confirma tu nuevo correo en FyTic",
        "action_label": "Confirmar cambio",
    },
}


def _build_html(action_url: str, action_label: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#0a0a14;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0a0a14;padding:48px 24px;">
    <tr><td align="center">
      <table width="100%" style="max-width:520px;background:#121220;border-radius:16px;border:1px solid rgba(255,255,255,0.08);overflow:hidden;">
        <tr>
          <td style="padding:40px 40px 24px;text-align:center;">
            <p style="margin:0 0 24px;font-size:11px;letter-spacing:0.4em;text-transform:uppercase;color:rgba(255,255,255,0.35);">
              FyTic &mdash; Investigación jurídica para México
            </p>
            <h1 style="margin:0 0 16px;font-size:28px;font-weight:300;color:#f9f9f9;line-height:1.2;">
              Un paso más
            </h1>
            <p style="margin:0 0 32px;font-size:15px;color:rgba(255,255,255,0.55);line-height:1.7;">
              Haz clic en el botón de abajo para continuar. El enlace expira en 24 horas.
            </p>
            <a href="{action_url}"
               style="display:inline-block;background:#f9f9f9;color:#0a0a14;font-size:13px;
                      font-weight:500;letter-spacing:0.08em;padding:14px 32px;
                      border-radius:100px;text-decoration:none;">
              {action_label}
            </a>
          </td>
        </tr>
        <tr>
          <td style="padding:24px 40px 40px;text-align:center;border-top:1px solid rgba(255,255,255,0.06);">
            <p style="margin:0;font-size:11px;color:rgba(255,255,255,0.25);line-height:1.6;">
              Si no solicitaste esto, ignora este correo.<br>
              FyTic &bull; Monterrey y CDMX, México
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _verify_hook_signature(request: Request) -> None:
    secret = os.environ.get("SUPABASE_HOOK_SECRET", "")
    if not secret:
        return  # Skip verification in dev (no secret configured)
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing hook authorization")
    try:
        pyjwt.decode(token, secret, algorithms=["HS256"])
    except pyjwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid hook signature")


@router.post("/auth/send-email")
async def send_email_hook(request: Request) -> JSONResponse:
    _verify_hook_signature(request)

    body = await request.json()
    user       = body.get("user", {})
    email_data = body.get("email_data", {})

    to_email    = user.get("email", "")
    action_type = email_data.get("email_action_type", "signup")
    token_hash  = email_data.get("token_hash", "")
    redirect_to = email_data.get("redirect_to", "")

    template = HOOK_EMAIL_TEMPLATES.get(action_type)
    if not template or not to_email or not token_hash:
        return JSONResponse({})

    site_url = os.environ.get("FRONTEND_URL", "https://fytic.tech")
    next_path = redirect_to or f"{site_url}/"
    action_url = (
        f"{site_url}/auth/callback"
        f"?token_hash={token_hash}"
        f"&type={'email' if action_type == 'signup' else action_type}"
        f"&next={next_path}"
    )

    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        return JSONResponse({})  # Resend not configured — skip silently

    resend.api_key = api_key
    resend.Emails.send({
        "from": "FyTic <noreply@fytic.tech>",
        "to": [to_email],
        "subject": template["subject"],
        "html": _build_html(action_url, template["action_label"]),
    })

    return JSONResponse({})
