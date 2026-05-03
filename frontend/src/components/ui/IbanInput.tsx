import { useEffect, useRef, useState } from 'react'
import client from '../../api/client'

interface IbanCheckResult {
  valid: boolean
  iban?: string
  bic?: string
  bank_name?: string
  error?: string
}

interface IbanInputProps {
  value: string
  onChange: (iban: string) => void
  onBicFound?: (bic: string, bankName: string) => void
  placeholder?: string
  className?: string
  disabled?: boolean
}

function validateIbanChecksum(iban: string): boolean {
  const clean = iban.replace(/\s/g, '').toUpperCase()
  if (clean.length < 15 || clean.length > 34) return false
  const rearranged = clean.slice(4) + clean.slice(0, 4)
  const numeric = rearranged.replace(/[A-Z]/g, c => String(c.charCodeAt(0) - 55))
  let remainder = 0
  for (const ch of numeric) {
    remainder = (remainder * 10 + parseInt(ch)) % 97
  }
  return remainder === 1
}

function formatIban(raw: string): string {
  const clean = raw.replace(/\s/g, '').toUpperCase()
  return clean.replace(/(.{4})/g, '$1 ').trim()
}

export function IbanInput({ value, onChange, onBicFound, placeholder = 'DE89 3704 0044…', className = '', disabled }: IbanInputProps) {
  const [status, setStatus] = useState<'idle' | 'checking' | 'valid' | 'invalid'>('idle')
  const [bankInfo, setBankInfo] = useState<string>('')
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const clean = value.replace(/\s/g, '').toUpperCase()

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current)

    if (!clean) {
      setStatus('idle')
      setBankInfo('')
      return
    }

    if (!validateIbanChecksum(clean)) {
      if (clean.length >= 15) setStatus('invalid')
      else setStatus('idle')
      setBankInfo('')
      return
    }

    setStatus('checking')
    timerRef.current = setTimeout(async () => {
      try {
        const res = await client.get<IbanCheckResult>('/iban-check/', { params: { iban: clean } })
        if (res.data.valid) {
          setStatus('valid')
          const info = res.data.bank_name || ''
          setBankInfo(info)
          if (onBicFound && res.data.bic) {
            onBicFound(res.data.bic, info)
          }
        } else {
          setStatus('invalid')
          setBankInfo(res.data.error || '')
        }
      } catch {
        setStatus('invalid')
        setBankInfo('')
      }
    }, 600)

    return () => { if (timerRef.current) clearTimeout(timerRef.current) }
  }, [clean])

  const borderClass =
    status === 'valid'   ? 'border-green-400 focus:ring-green-300' :
    status === 'invalid' ? 'border-red-400 focus:ring-red-300'     :
    'border-gray-300 focus:ring-primary-300'

  return (
    <div className="w-full">
      <div className="relative">
        <input
          type="text"
          value={formatIban(value)}
          onChange={e => onChange(e.target.value.replace(/\s/g, '').toUpperCase())}
          placeholder={placeholder}
          disabled={disabled}
          className={`border rounded px-3 py-2 text-sm font-mono w-full focus:outline-none focus:ring-2 transition-colors ${borderClass} ${className}`}
          spellCheck={false}
          autoComplete="off"
        />
        {status === 'checking' && (
          <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-gray-400">…</span>
        )}
        {status === 'valid' && (
          <span className="absolute right-2 top-1/2 -translate-y-1/2 text-green-500 text-sm">✓</span>
        )}
        {status === 'invalid' && clean.length >= 15 && (
          <span className="absolute right-2 top-1/2 -translate-y-1/2 text-red-500 text-sm">✗</span>
        )}
      </div>
      {status === 'valid' && bankInfo && (
        <p className="text-xs text-green-700 mt-0.5 pl-0.5">{bankInfo}</p>
      )}
      {status === 'invalid' && clean.length >= 15 && (
        <p className="text-xs text-red-600 mt-0.5 pl-0.5">
          {bankInfo || 'Ungültige IBAN'}
        </p>
      )}
    </div>
  )
}
