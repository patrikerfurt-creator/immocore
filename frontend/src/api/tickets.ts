import client from './client'
import type { Ticket, TicketList } from '../types'

export const ticketsApi = {
  list: (params?: Record<string, string>) =>
    client.get<TicketList[]>('/tickets/', { params }).then(r => r.data),
  get: (id: string) => client.get<Ticket>(`/tickets/${id}/`).then(r => r.data),
  create: (data: Partial<Ticket>) => client.post<Ticket>('/tickets/', data).then(r => r.data),
  update: (id: string, data: Partial<Ticket>) =>
    client.patch<Ticket>(`/tickets/${id}/`, data).then(r => r.data),
  delete: (id: string) => client.delete(`/tickets/${id}/`),

  statusAendern: (id: string, status: string) =>
    client.patch(`/tickets/${id}/`, { status }).then(r => r.data),
  zuweisen: (id: string, userId: number) =>
    client.post(`/tickets/${id}/zuweisen/`, { user: userId }).then(r => r.data),
}
