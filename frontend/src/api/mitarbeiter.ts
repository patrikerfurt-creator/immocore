import client from './client'
import type { Mitarbeiter, MitarbeiterZuordnung } from '../types'

export const mitarbeiterApi = {
  list: (params?: Record<string, string>) =>
    client.get<Mitarbeiter[]>('/mitarbeiter/', { params }).then(r => r.data),

  get: (id: string) =>
    client.get<Mitarbeiter>(`/mitarbeiter/${id}/`).then(r => r.data),

  create: (data: Partial<Mitarbeiter> & { passwort?: string }) =>
    client.post<Mitarbeiter>('/mitarbeiter/', data).then(r => r.data),

  update: (id: string, data: Partial<Mitarbeiter> & { passwort?: string }) =>
    client.patch<Mitarbeiter>(`/mitarbeiter/${id}/`, data).then(r => r.data),

  delete: (id: string) => client.delete(`/mitarbeiter/${id}/`),
}

export const zuordnungApi = {
  listByObjekt: (objektId: string) =>
    client.get<MitarbeiterZuordnung[]>('/mitarbeiter-zuordnungen/', { params: { objekt: objektId } }).then(r => r.data),

  create: (mitarbeiterId: number, objektId: string, aufgabe: string) =>
    client.post<MitarbeiterZuordnung>('/mitarbeiter-zuordnungen/', {
      mitarbeiter: mitarbeiterId,
      objekt: objektId,
      aufgabe,
    }).then(r => r.data),

  updateAufgabe: (id: number, aufgabe: string) =>
    client.patch<MitarbeiterZuordnung>(`/mitarbeiter-zuordnungen/${id}/`, { aufgabe }).then(r => r.data),

  delete: (id: number) => client.delete(`/mitarbeiter-zuordnungen/${id}/`),
}
