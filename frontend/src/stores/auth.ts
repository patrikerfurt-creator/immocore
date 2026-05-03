import { create } from 'zustand'
import { login as apiLogin } from '../api/auth'
import client from '../api/client'

interface AuthState {
  isAuthenticated: boolean
  username: string | null
  gruppen: string[]
  istFrontoffice: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  ladeGruppen: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set) => ({
  isAuthenticated: !!localStorage.getItem('access_token'),
  username: localStorage.getItem('username'),
  gruppen: JSON.parse(localStorage.getItem('gruppen') ?? '[]'),
  istFrontoffice: JSON.parse(localStorage.getItem('gruppen') ?? '[]').includes('Frontoffice'),

  login: async (username, password) => {
    const tokens = await apiLogin(username, password)
    localStorage.setItem('access_token', tokens.access)
    localStorage.setItem('refresh_token', tokens.refresh)
    localStorage.setItem('username', username)
    set({ isAuthenticated: true, username })
    // Gruppen nachladen
    const { data } = await client.get<{ gruppen: string[] }>('/me/')
    const gruppen = data.gruppen ?? []
    localStorage.setItem('gruppen', JSON.stringify(gruppen))
    set({ gruppen, istFrontoffice: gruppen.includes('Frontoffice') })
  },

  logout: () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('username')
    localStorage.removeItem('gruppen')
    set({ isAuthenticated: false, username: null, gruppen: [], istFrontoffice: false })
  },

  ladeGruppen: async () => {
    try {
      const { data } = await client.get<{ gruppen: string[] }>('/me/')
      const gruppen = data.gruppen ?? []
      localStorage.setItem('gruppen', JSON.stringify(gruppen))
      set({ gruppen, istFrontoffice: gruppen.includes('Frontoffice') })
    } catch {
      // ignorieren — kein Netz oder nicht eingeloggt
    }
  },
}))
