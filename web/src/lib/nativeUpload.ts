/**
 * Promote upload from the iOS shell: Files / iCloud picker and camera-as-scanner.
 * The existing `/documents` API still accepts only PDF/DOCX. A camera JPEG is
 * wrapped as a one-page PDF so we do not invent a new ingestion MIME type.
 */
import { callPlugin, PluginUnavailableError } from './capacitorBridge'
import { isJpeg, jpegToPdf } from './jpegPdf'
import { currentHost, type CapacitorHost } from './platform'

export const PDF_MIME = 'application/pdf'
export const DOCX_MIME =
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document'

/** Same 415 the API returns — shown before upload when a capture cannot be wrapped. */
export const READING_LIST_TYPE_LIMIT =
  'Upload a PDF or a Word document — that is what a reading list comes as.'

export const IOS_SETTINGS_ACCESS =
  'Allow access in iOS Settings → BadgeDay, then try again. You can still add a PDF or Word file from Files.'

export type PickedUpload = {
  file: File
  source: 'files' | 'camera'
}

function decodeBase64(data: string): Uint8Array {
  const binary = atob(data)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i)
  return bytes
}

function asFile(bytes: Uint8Array, name: string, type: string): File {
  const copy = new Uint8Array(bytes)
  return new File([copy], name, { type })
}

export function isPermissionDenied(caught: unknown): boolean {
  const message = caught instanceof Error ? caught.message : String(caught)
  const lower = message.toLowerCase()
  return (
    lower.includes('denied') ||
    lower.includes('permission') ||
    lower.includes('not authorized') ||
    lower.includes('unauthorized') ||
    lower.includes('access to camera') ||
    lower.includes('access to photos')
  )
}

export function isUserCancel(caught: unknown): boolean {
  const message = caught instanceof Error ? caught.message : String(caught)
  const lower = message.toLowerCase()
  return (
    lower.includes('cancel') ||
    lower.includes('dismiss') ||
    lower.includes('user cancelled') ||
    lower.includes('no files selected')
  )
}

function uploadableFromBytes(bytes: Uint8Array, filename: string, mime: string | undefined): File {
  const type = (mime || '').toLowerCase()
  if (type === PDF_MIME || filename.toLowerCase().endsWith('.pdf')) {
    return asFile(bytes, filename.endsWith('.pdf') ? filename : `${filename}.pdf`, PDF_MIME)
  }
  if (type === DOCX_MIME || filename.toLowerCase().endsWith('.docx')) {
    return asFile(bytes, filename.endsWith('.docx') ? filename : `${filename}.docx`, DOCX_MIME)
  }
  if (isJpeg(bytes) || type === 'image/jpeg' || type === 'image/jpg') {
    return asFile(jpegToPdf(bytes), 'scan.pdf', PDF_MIME)
  }
  throw new Error(READING_LIST_TYPE_LIMIT)
}

export async function pickPromoteDocument(
  host: CapacitorHost = currentHost(),
): Promise<PickedUpload | null> {
  try {
    const result = await callPlugin<{
      files?: Array<{ name?: string; mimeType?: string; data?: string }>
    }>(
      'FilePicker',
      'pickFiles',
      {
        types: [PDF_MIME, DOCX_MIME],
        limit: 1,
        readData: true,
      },
      host,
    )
    const picked = result.files?.[0]
    if (!picked?.data) return null
    const bytes = decodeBase64(picked.data)
    return {
      file: uploadableFromBytes(bytes, picked.name || 'document.pdf', picked.mimeType),
      source: 'files',
    }
  } catch (caught) {
    if (caught instanceof PluginUnavailableError) throw caught
    if (isUserCancel(caught)) return null
    if (isPermissionDenied(caught)) throw new Error(IOS_SETTINGS_ACCESS)
    throw caught instanceof Error ? caught : new Error(READING_LIST_TYPE_LIMIT)
  }
}

export async function scanPromotePage(
  host: CapacitorHost = currentHost(),
): Promise<PickedUpload | null> {
  try {
    const photo = await callPlugin<{ base64String?: string; format?: string }>(
      'Camera',
      'getPhoto',
      {
        source: 'CAMERA',
        resultType: 'base64',
        quality: 80,
        correctOrientation: true,
      },
      host,
    )
    if (!photo.base64String) return null
    const bytes = decodeBase64(photo.base64String)
    if (!isJpeg(bytes)) {
      throw new Error(READING_LIST_TYPE_LIMIT)
    }
    return { file: asFile(jpegToPdf(bytes), 'scan.pdf', PDF_MIME), source: 'camera' }
  } catch (caught) {
    if (caught instanceof PluginUnavailableError) throw caught
    if (isUserCancel(caught)) return null
    if (isPermissionDenied(caught)) throw new Error(IOS_SETTINGS_ACCESS)
    throw caught instanceof Error ? caught : new Error(READING_LIST_TYPE_LIMIT)
  }
}
