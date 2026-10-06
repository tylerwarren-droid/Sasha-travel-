/**
 * Sasha 159 (1) · PHOTOS IN THE WEB CHAT: whatever the browser gives (attach, drag-and-drop, Cmd-V, a phone's camera or
 * library) becomes a JPEG at most 1800 px on its long side, so a DNI's or passport's text stays readable and five photos
 * fit in one chat request. Read in the browser; sent once with the message; nothing is kept here.
 */
export type Attachment = { name: string; content_type: 'image/jpeg'; data_b64: string; preview: string }

export const MAX_PHOTOS = 5
const LONG_SIDE = 1800

export async function toJpeg(file: File): Promise<Attachment> {
  const url = URL.createObjectURL(file)
  try {
    const img = await new Promise<HTMLImageElement>((ok, fail) => {
      const i = new Image()
      i.onload = () => ok(i)
      i.onerror = () => fail(new Error(`${file.name || 'that photo'} can't be opened in this browser (try a JPEG or PNG)`))
      i.src = url
    })
    const k = Math.min(1, LONG_SIDE / Math.max(img.naturalWidth, img.naturalHeight))
    const c = document.createElement('canvas')
    c.width = Math.round(img.naturalWidth * k)
    c.height = Math.round(img.naturalHeight * k)
    const g = c.getContext('2d')
    if (!g) throw new Error('this browser cannot prepare photos')
    g.fillStyle = '#fff'
    g.fillRect(0, 0, c.width, c.height)
    g.drawImage(img, 0, 0, c.width, c.height)
    const dataUrl = c.toDataURL('image/jpeg', 0.86)
    return { name: file.name || 'photo.jpg', content_type: 'image/jpeg', data_b64: dataUrl.split(',')[1], preview: dataUrl }
  } finally {
    URL.revokeObjectURL(url)
  }
}

export function imagesOf(list: FileList | File[] | null | undefined): File[] {
  return Array.from(list ?? []).filter((f) => f.type.startsWith('image/') || /\.(heic|heif|jpe?g|png|webp)$/i.test(f.name))
}
