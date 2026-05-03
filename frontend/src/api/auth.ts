import axios from 'axios'
import type { TokenPair } from '../types'

export async function login(username: string, password: string): Promise<TokenPair> {
  const { data } = await axios.post<TokenPair>('/api/v1/auth/token/', { username, password })
  return data
}

export async function refreshToken(refresh: string): Promise<{ access: string }> {
  const { data } = await axios.post('/api/v1/auth/token/refresh/', { refresh })
  return data
}
