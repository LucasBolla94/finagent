import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'FinAgent — Seu Assistente Financeiro',
  description: 'Controle suas finanças com inteligência artificial',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  )
}
