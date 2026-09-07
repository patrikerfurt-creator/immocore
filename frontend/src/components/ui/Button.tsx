import { ButtonHTMLAttributes } from 'react'

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost' | 'portal' | 'portal-secondary'
  size?: 'sm' | 'md'
}

const base = 'inline-flex items-center justify-center rounded font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-offset-1 disabled:opacity-50 disabled:cursor-not-allowed'

const variants = {
  primary:   'bg-primary-600 text-white hover:bg-primary-700 focus:ring-primary-500',
  secondary: 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50 focus:ring-primary-500',
  danger:    'bg-red-600 text-white hover:bg-red-700 focus:ring-red-500',
  ghost:     'text-gray-600 hover:bg-gray-100 focus:ring-primary-500',
  // Nur für das Eigentümer-Portal (Mockup-Palette). Bewusst als eigene
  // Variante statt als Umfärbung von 'primary': 'primary' wird in der
  // gesamten Verwaltungsoberfläche benutzt und muss blau bleiben.
  portal:              'bg-portal-brand text-white hover:bg-[#26493f] focus:ring-portal-brand',
  'portal-secondary':  'bg-white text-portal-ink border border-portal-line hover:bg-portal-paper focus:ring-portal-brand',
}

const sizes = {
  sm: 'px-3 py-1.5 text-sm gap-1.5',
  md: 'px-4 py-2 text-sm gap-2',
}

export function Button({ variant = 'primary', size = 'md', className = '', children, ...props }: Props) {
  return (
    <button className={`${base} ${variants[variant]} ${sizes[size]} ${className}`} {...props}>
      {children}
    </button>
  )
}
