import { esES } from '@clerk/localizations'

const subtitle = 'para continuar en AnexosFácil'

/**
 * Clerk's esES mixes "usted" with "tú" and names the app from the Clerk
 * dashboard. The app speaks "tú" and is called AnexosFácil, so the strings the
 * sign-in and sign-up flows show are overridden here.
 */
export const clerkLocalization = {
  ...esES,
  formFieldInputPlaceholder__emailAddress: 'tu@correo.com',
  formFieldInputPlaceholder__emailAddress_username:
    'Tu correo o nombre de usuario',
  signIn: {
    ...esES.signIn,
    start: {
      ...esES.signIn?.start,
      title: 'Iniciar sesión',
      subtitle,
      actionLink: 'Crea una',
    },
    emailCode: {
      ...esES.signIn?.emailCode,
      title: 'Revisa tu correo',
      subtitle,
    },
    emailLink: {
      ...esES.signIn?.emailLink,
      title: 'Revisa tu correo',
      subtitle,
      formSubtitle: 'Usa el enlace de verificación que enviamos a tu correo',
    },
    password: {
      ...esES.signIn?.password,
      title: 'Escribe tu contraseña',
      subtitle,
    },
  },
  signUp: {
    ...esES.signUp,
    start: {
      ...esES.signUp?.start,
      title: 'Crear cuenta',
      subtitle,
      subtitleCombined: subtitle,
    },
    continue: {
      ...esES.signUp?.continue,
      title: 'Completa los datos que faltan',
      subtitle,
      actionText: '¿Ya tienes una cuenta?',
      actionLink: 'Inicia sesión',
    },
    emailCode: {
      ...esES.signUp?.emailCode,
      title: 'Verifica tu correo',
      subtitle,
      formSubtitle: 'Escribe el código que enviamos a tu correo',
      resendButton: 'Reenviar código',
    },
    emailLink: {
      ...esES.signUp?.emailLink,
      subtitle,
      formSubtitle: 'Usa el enlace de verificación que enviamos a tu correo',
    },
  },
}
