/**
 * Turns an API failure into a message a customer can read.
 *
 * The backend's stable error codes map to translated copy; anything unmapped
 * falls back to a generic message. A raw backend exception must never reach the
 * screen (spec §70).
 */
import { useI18n } from 'vue-i18n'
import { ApiRequestError } from '~/utils/api-client'
import { useUiStore } from '~/stores/ui'

export function useApiError() {
  const { t, te } = useI18n()
  const ui = useUiStore()

  /** Human-readable message for any thrown value. */
  function messageFor(error: unknown): string {
    if (error instanceof ApiRequestError) {
      const key = `errors.${error.code}`
      if (te(key)) return t(key)
      // The API's own message is already localised and safe to show.
      return error.message || t('errors.generic')
    }

    if (error instanceof TypeError) return t('errors.network')
    return t('errors.generic')
  }

  /** Field-level messages for binding to form inputs. */
  function fieldErrorsFor(error: unknown): Record<string, string[]> {
    return error instanceof ApiRequestError ? error.fieldErrors : {}
  }

  /** Show the failure as a snackbar and return the message. */
  function notify(error: unknown): string {
    const message = messageFor(error)
    ui.error(message)
    return message
  }

  return { messageFor, fieldErrorsFor, notify }
}
