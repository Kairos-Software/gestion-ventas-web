/* ================================================================
   Datos de mentira para la maqueta.
   Reproducen la forma de lo que hoy devuelven las vistas reales
   (BuscarProductoAjax, BuscarClienteAjax, construir_contexto_detalle)
   pero fijos y sin servidor.
   ================================================================ */
window.MOCK = {

  empresa: {
    nombre: 'Kairos — Almacén y Bebidas',
    cuit: '30-71111222-3',
    domicilio: 'Av. Siempreviva 742, Springfield',
    condicion_iva: 'Responsable Inscripto',
  },

  /* ---- Productos ---- */
  productos: [
    { pk: 1,  codigo: 'PRD-0001', nombre: 'Coca-Cola 1.5L',           marca: 'Coca-Cola',    categoria_id: 1, precio: 1850, stock: 48,   gestiona_stock: true,  tipo: 'simple' },
    { pk: 2,  codigo: 'PRD-0002', nombre: 'Agua Mineral 2L',          marca: 'Villavicencio',categoria_id: 1, precio: 1200, stock: 0,    gestiona_stock: true,  tipo: 'simple' },
    { pk: 3,  codigo: 'PRD-0003', nombre: 'Yerba Mate 1kg',           marca: 'Playadito',    categoria_id: 2, precio: 3400, stock: 20,   gestiona_stock: true,  tipo: 'simple' },
    { pk: 4,  codigo: 'PRD-0004', nombre: 'Fideos Guiseros 500g',     marca: 'Lucchetti',    categoria_id: 2, precio: 980,  stock: 60,   gestiona_stock: true,  tipo: 'simple' },
    { pk: 5,  codigo: 'PRD-0005', nombre: 'Aceite Girasol 900ml',     marca: 'Natura',       categoria_id: 2, precio: 2600, stock: 35,   gestiona_stock: true,  tipo: 'simple' },
    { pk: 6,  codigo: 'PRD-0006', nombre: 'Remera lisa algodón',      marca: 'Genérica',     categoria_id: 3, precio: 9900, stock: 12,   gestiona_stock: true,  tipo: 'variantes',
      combinaciones: [
        { combinacion_pk: 61, nombre: 'Talle S · Negro',  stock: 3 },
        { combinacion_pk: 62, nombre: 'Talle M · Negro',  stock: 5 },
        { combinacion_pk: 63, nombre: 'Talle L · Blanco', stock: 4 },
      ] },
    { pk: 7,  codigo: 'PRD-0007', nombre: 'Queso Cremoso (x kg)',     marca: 'La Paulina',   categoria_id: 2, precio: 8200, stock: 15.5, gestiona_stock: true,  tipo: 'pesable' },
    { pk: 8,  codigo: 'PRD-0008', nombre: 'Pan Lactal 500g',          marca: 'Bimbo',        categoria_id: 2, precio: 2100, stock: 18,   gestiona_stock: true,  tipo: 'simple' },
    { pk: 9,  codigo: 'PRD-0009', nombre: 'Cerveza Rubia 1L',         marca: 'Quilmes',      categoria_id: 1, precio: 2450, stock: 40,   gestiona_stock: true,  tipo: 'simple' },
    { pk: 10, codigo: 'PRD-0010', nombre: 'Detergente 750ml',         marca: 'Magistral',    categoria_id: 4, precio: 1750, stock: 22,   gestiona_stock: true,  tipo: 'simple' },
    { pk: 11, codigo: 'PRD-0011', nombre: 'Servicio de flete/entrega',marca: '',             categoria_id: 9, precio: 15000,stock: null, gestiona_stock: false, tipo: 'simple' },
    { pk: 12, codigo: 'PRD-0012', nombre: 'Café molido 250g',         marca: 'La Virginia',  categoria_id: 2, precio: 4200, stock: 14,   gestiona_stock: true,  tipo: 'simple' },
  ],

  /* Lotes / etiquetas de balanza que se pueden "escanear" tipeando el código */
  lotes: {
    'LT-2025-0003': { producto_pk: 3, lote_codigo: 'LT-2025-0003' },          // Yerba, lote puntual
    'LT-2025-0009': { producto_pk: 9, lote_codigo: 'LT-2025-0009' },          // Cerveza, lote puntual
  },
  balanzas: {
    'BAL-2025-0007': { producto_pk: 7, etiqueta_codigo: 'BAL-2025-0007', cantidad_fija: 0.850, precio_fijo: 6970 },
  },

  /* ---- Clientes ---- (con scoring de riesgo de pago) ---- */
  clientes: [
    { pk: 2, nombre: 'Martín Gómez',                doc: 'DNI 30.111.222',    tipo: 'persona', scoring: 812, banda: 'excelente', label: 'Excelente' },
    { pk: 3, nombre: 'Distribuidora El Sol S.A.',   doc: 'CUIT 30-71234567-9',tipo: 'empresa', scoring: 640, banda: 'regular',   label: 'Regular',
      alerta: 'Tiene 1 cuota vencida hace 8 días.' },
    { pk: 4, nombre: 'Laura Fernández',             doc: 'DNI 27.888.999',    tipo: 'persona', scoring: 305, banda: 'riesgo',    label: 'Riesgo',
      alerta: '2 cheques rechazados en los últimos 90 días.' },
    { pk: 5, nombre: 'Kiosco 24hs',                 doc: 'CUIT 20-33444555-6',tipo: 'empresa', scoring: 120, banda: 'critico',   label: 'Crítico',
      alerta: 'Mora de $ 340.000 hace 45 días.' },
    { pk: 6, nombre: 'Nuevo Cliente SRL',           doc: 'CUIT 30-99888777-1',tipo: 'empresa', scoring: null, sinHistorial: true },
    { pk: 7, nombre: 'Panadería La Esquina',        doc: 'CUIT 27-22333444-5',tipo: 'empresa', scoring: 760, banda: 'bueno',     label: 'Bueno' },
  ],

  /* ---- Listas de descuento ---- */
  listasDescuento: [
    { nombre: 'Mayorista', porcentaje: 12 },
    { nombre: 'Empleados', porcentaje: 20 },
  ],

  /* ---- Ofertas vigentes hoy ---- */
  ofertas: [
    { nombre: '2x1 en Coca-Cola', tipo: 'nxm', cantidad_lleva: 2, cantidad_paga: 1, porcentaje: null, aplicacion: 'automatica', productos: [1], categorias: [] },
    { nombre: 'Yerba -15%',       tipo: 'porcentaje', porcentaje: 15, aplicacion: 'manual', productos: [3], categorias: [] },
    { nombre: 'Compra +$40.000: -10%', tipo: 'umbral', porcentaje: 10, monto_minimo: 40000, base_calculo: 'neto', aplicacion: 'automatica', productos: [], categorias: [] },
  ],

  /* ---- Cuentas reales (a dónde entra la plata). Efectivo se resuelve solo. ---- */
  cuentas: [
    { pk: 2, nombre: 'Banco Galicia CC',  moneda: 'ARS', titular: 'Kairos SRL',  acepta_debito: true,  acepta_credito: true,  acepta_qr: false, acepta_transferencia: true },
    { pk: 3, nombre: 'Mercado Pago',      moneda: 'ARS', titular: 'Kairos SRL',  acepta_debito: true,  acepta_credito: true,  acepta_qr: true,  acepta_transferencia: true },
    { pk: 4, nombre: 'Caja en USD',       moneda: 'USD', titular: '',            acepta_debito: false, acepta_credito: false, acepta_qr: false, acepta_transferencia: true },
  ],

  /* ---- Tarjetas / billeteras del cliente (definen el recargo) ---- */
  tarjetas: [
    { pk: 1, nombre: 'Visa',           acepta_debito: true,  acepta_credito: true,  acepta_qr: false, acepta_transferencia: false },
    { pk: 2, nombre: 'Mastercard',     acepta_debito: true,  acepta_credito: true,  acepta_qr: false, acepta_transferencia: false },
    { pk: 3, nombre: 'Mercado Pago QR',acepta_debito: false, acepta_credito: false, acepta_qr: true,  acepta_transferencia: false },
    { pk: 4, nombre: 'Naranja X',      acepta_debito: false, acepta_credito: true,  acepta_qr: false, acepta_transferencia: false },
  ],

  /* ---- Recargos configurados (tarjeta + medio + cantidad de pagos) ---- */
  recargos: [
    { tarjeta_pk: 1, medio: 'debito',   cantidad_pagos: 1, etiqueta_plan: 'Débito',   nombre_plan: '',        recargo_pct: 0 },
    { tarjeta_pk: 1, medio: 'credito',  cantidad_pagos: 1, etiqueta_plan: '1 pago',   nombre_plan: '',        recargo_pct: 0 },
    { tarjeta_pk: 1, medio: 'credito',  cantidad_pagos: 3, etiqueta_plan: '3 cuotas', nombre_plan: 'Plan 3',  recargo_pct: 12 },
    { tarjeta_pk: 1, medio: 'credito',  cantidad_pagos: 6, etiqueta_plan: '6 cuotas', nombre_plan: 'Plan 6',  recargo_pct: 25 },
    { tarjeta_pk: 2, medio: 'debito',   cantidad_pagos: 1, etiqueta_plan: 'Débito',   nombre_plan: '',        recargo_pct: 0 },
    { tarjeta_pk: 2, medio: 'credito',  cantidad_pagos: 3, etiqueta_plan: '3 cuotas', nombre_plan: 'Plan 3',  recargo_pct: 15 },
    { tarjeta_pk: 3, medio: 'qr',       cantidad_pagos: 1, etiqueta_plan: 'QR',       nombre_plan: '',        recargo_pct: 0 },
    { tarjeta_pk: 4, medio: 'credito',  cantidad_pagos: 3, etiqueta_plan: '3 cuotas', nombre_plan: 'Plan Z',  recargo_pct: 18 },
    { tarjeta_pk: 4, medio: 'credito',  cantidad_pagos: 6, etiqueta_plan: '6 cuotas', nombre_plan: 'Plan Z6', recargo_pct: 34 },
  ],

  /* ---- Medios de pago disponibles ---- */
  medios: [
    { value: 'efectivo',      label: 'Efectivo' },
    { value: 'debito',        label: 'Débito' },
    { value: 'credito',       label: 'Crédito' },
    { value: 'qr',            label: 'QR / Billetera' },
    { value: 'transferencia', label: 'Transferencia' },
    { value: 'cuotas',        label: 'Cuotas (financia el local)' },
    { value: 'cheque',        label: 'Cheque' },
  ],
};
