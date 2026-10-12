import { useCallback, useEffect, useRef, useState } from 'react'
import { Button } from '../Button'

const VIEW = 280 // on-screen square, CSS pixels
const OUTPUT = 1024 // the square sent to the server (it resizes to 512x512)
const STEP = 12 // pixels per arrow key press

interface Props {
  /** The chosen file, as a data: URL (the page's CSP allows data: images, not blob:). */
  source: string
  isPending: boolean
  onCancel: () => void
  onCrop: (photo: Blob) => void
}

/**
 * Square crop: drag (or use the arrow keys) to place the face, zoom with the slider. The
 * result is re-drawn on a canvas and sent as a JPEG, so nothing of the original file
 * (EXIF, location) leaves the device; the server checks and strips again anyway.
 */
export function PhotoCropper({ source, isPending, onCancel, onCrop }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [image, setImage] = useState<HTMLImageElement | null>(null)
  const [failed, setFailed] = useState(false)
  const [zoom, setZoom] = useState(1)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const drag = useRef<{ x: number; y: number } | null>(null)

  useEffect(() => {
    const loaded = new Image()
    loaded.onload = () => setImage(loaded)
    loaded.onerror = () => setFailed(true)
    loaded.src = source
  }, [source])

  /** Where the image is drawn in the square, kept so that it always covers it. */
  const placement = useCallback(
    (size: number) => {
      if (!image) return null
      const scale = Math.max(size / image.naturalWidth, size / image.naturalHeight) * zoom
      const width = image.naturalWidth * scale
      const height = image.naturalHeight * scale
      const ratio = size / VIEW
      const clamp = (value: number, extent: number) => Math.min(0, Math.max(size - extent, value))
      return {
        x: clamp((size - width) / 2 + offset.x * ratio, width),
        y: clamp((size - height) / 2 + offset.y * ratio, height),
        width,
        height,
      }
    },
    [image, zoom, offset],
  )

  useEffect(() => {
    const context = canvasRef.current?.getContext('2d')
    const where = placement(VIEW)
    if (!context || !image || !where) return
    context.clearRect(0, 0, VIEW, VIEW)
    context.drawImage(image, where.x, where.y, where.width, where.height)
  }, [image, placement])

  /** Keep the offset within what still covers the square (no "dead" drag past an edge). */
  const limit = useCallback(
    (point: { x: number; y: number }, scaleZoom: number) => {
      if (!image) return point
      const scale = Math.max(VIEW / image.naturalWidth, VIEW / image.naturalHeight) * scaleZoom
      const spareX = (image.naturalWidth * scale - VIEW) / 2
      const spareY = (image.naturalHeight * scale - VIEW) / 2
      return { x: Math.max(-spareX, Math.min(spareX, point.x)), y: Math.max(-spareY, Math.min(spareY, point.y)) }
    },
    [image],
  )

  function move(dx: number, dy: number) {
    setOffset((current) => limit({ x: current.x + dx, y: current.y + dy }, zoom))
  }

  function crop() {
    const where = placement(OUTPUT)
    if (!image || !where) return
    const canvas = document.createElement('canvas')
    canvas.width = OUTPUT
    canvas.height = OUTPUT
    const context = canvas.getContext('2d')
    if (!context) return
    context.drawImage(image, where.x, where.y, where.width, where.height)
    canvas.toBlob((blob) => { if (blob) onCrop(blob) }, 'image/jpeg', 0.9)
  }

  if (failed) {
    return (
      <div className="flex flex-col gap-3">
        <p role="alert" className="text-sm text-red-700">Não foi possível abrir esta imagem. Escolhe uma fotografia em JPEG ou PNG.</p>
        <Button variant="secondary" onClick={onCancel}>Voltar</Button>
      </div>
    )
  }

  return (
    <div className="flex flex-col items-center gap-4">
      <canvas
        ref={canvasRef}
        width={VIEW}
        height={VIEW}
        tabIndex={0}
        role="img"
        aria-label="Pré-visualização do recorte. Usa as setas para mover a foto."
        className="touch-none cursor-move rounded-full bg-slate-100 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-teal-700"
        style={{ width: VIEW, height: VIEW, maxWidth: '100%' }}
        onPointerDown={(event) => {
          drag.current = { x: event.clientX, y: event.clientY }
          event.currentTarget.setPointerCapture?.(event.pointerId)
        }}
        onPointerMove={(event) => {
          if (!drag.current) return
          move(event.clientX - drag.current.x, event.clientY - drag.current.y)
          drag.current = { x: event.clientX, y: event.clientY }
        }}
        onPointerUp={() => { drag.current = null }}
        onKeyDown={(event) => {
          const moves: Record<string, [number, number]> = { ArrowLeft: [-STEP, 0], ArrowRight: [STEP, 0], ArrowUp: [0, -STEP], ArrowDown: [0, STEP] }
          const delta = moves[event.key]
          if (delta) {
            event.preventDefault()
            move(...delta)
          }
        }}
      />
      <label className="flex w-full max-w-xs flex-col gap-1 text-sm font-medium text-slate-700">
        Zoom
        <input type="range" min={1} max={3} step={0.05} value={zoom} onChange={(event) => {
          const next = Number(event.target.value)
          setZoom(next)
          setOffset((current) => limit(current, next))
        }} />
      </label>
      <p className="text-center text-sm text-slate-600">O rosto deve ficar centrado e bem visível dentro do círculo.</p>
      <div className="flex flex-wrap justify-center gap-3">
        <Button variant="secondary" disabled={isPending} onClick={onCancel}>Cancelar</Button>
        <Button variant="secondary" disabled={isPending} onClick={() => { setZoom(1); setOffset({ x: 0, y: 0 }) }}>Centrar</Button>
        <Button isLoading={isPending} disabled={!image} onClick={crop}>Enviar para aprovação</Button>
      </div>
    </div>
  )
}
