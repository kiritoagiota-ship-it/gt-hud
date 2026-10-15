"""O desenho do rosto do Umbra (fragment shader GLSL ES 1.0).

GERADO por ferramentas/umbra_shader.py a partir de ferramentas/umbra_previa.html: não edite aqui,
edite a página (e confira no navegador) e rode a ferramenta de novo.
"""
FONTE = r'''#ifdef GL_ES
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
#endif
uniform vec2 u_res;
#ifdef NO_APP
varying vec2 tex_coord0;       // (o Kivy passa: 0 a 1 no retângulo do rosto)
uniform float u_presenca;      // aparecendo/sumindo (0 a 1)
#endif
uniform float u_t, u_boca, u_olho, u_inclina, u_feliz, u_torto, u_alerta, u_escuta;
uniform vec2 u_giro, u_olhar;                          // cabeça virando (x) e acenando (y); para onde ele olha
uniform float u_rolar, u_palpebra, u_enfase, u_brilho; // cabeça de lado; pálpebra descendo; sílaba forte; força do brilho
uniform float u_dentes;                                // dentes ainda maiores: animado, contente, ameaçando (0 a 1)
const vec3 AZUL = vec3(0.353, 0.627, 1.0);
const vec3 ROXO = vec3(0.608, 0.361, 1.0);
const vec3 LARANJA = vec3(1.0, 0.59, 0.2);
const vec3 VERDE = vec3(0.36, 1.0, 0.78);
// o Umbra v2 (dono, 15/10/2026): refeito a partir da imagem de referência dele, com as cores, a silhueta e as
// medidas tiradas da própria imagem (olhos e boca abaixo). Os controles são os mesmos de antes.
#define OLHO_X 0.385
#define OLHO_Y -0.165
#define OLHO_ANG 34.0
#define OLHO_MEIA 0.31
#define OLHO_BAIXO 0.150
#define OLHO_CIMA 0.060
#define BOCA_CANTO 0.160
#define BOCA_AMP 0.195
#define BOCA_MEIA 0.44
const float BOCA_PARADA = 0.200;
const float GENGIVA_VISTA = 0.006;      // quanto da gengiva aparece com a boca parada
vec3 col;
float alfa;

float sq(float v) { return v * v; }
void por(vec3 c, float a) { a = clamp(a, 0.0, 1.0); col = c * a + col * (1.0 - a); alfa = a + alfa * (1.0 - a); }
void luz(vec3 c, float f) { f = clamp(f, 0.0, 1.0); col = min(col + c * f, vec3(1.0)); alfa = clamp(alfa + f * 0.85, 0.0, 1.0); }
float deg(float a, float b, float v) { float t = clamp((v - a) / (b - a), 0.0, 1.0); return t * t * (3.0 - 2.0 * t); }
float h21(vec2 p) { p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32); return fract(p.x * p.y); }
float rnd(float k) { return fract(sin(k * 12.9898 + 78.233) * 43758.5453); }
float vn(vec2 p) {
  vec2 i = floor(p), f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  return mix(mix(h21(i), h21(i + vec2(1.0, 0.0)), f.x), mix(h21(i + vec2(0.0, 1.0)), h21(i + vec2(1.0, 1.0)), f.x), f.y);
}
float fbm(vec2 p) { float s = 0.0, a = 0.5; for (int i = 0; i < 5; i++) { s += a * vn(p); p = p * 2.03 + vec2(17.1, 9.2); a *= 0.5; } return s / 0.96875; }
float fbm3(vec2 p) { float s = 0.0, a = 0.5; for (int i = 0; i < 3; i++) { s += a * vn(p); p = p * 2.03 + vec2(17.1, 9.2); a *= 0.5; } return s / 0.875; }

float pele;       // quanto deste ponto é cabeça (0 fora, 1 dentro): os olhos usam para não sujar o fundo

// ---- a boca em duas peças: a GENGIVA com os dentes (presa ao crânio em cima e à mandíbula embaixo: os
// dentes andam só com o osso, como peças rígidas) e os LÁBIOS por cima (abrem com a mandíbula, repuxam nas
// sílabas fortes e no alerta, esticam os cantos com a boca bem aberta), cobrindo e revelando os dentes.
float meiaDentes() { return BOCA_MEIA + 0.03 * u_feliz; }                 // o arco dos dentes (não estica)
float abreMand() { return 0.30 * u_boca; }                          // quanto a mandíbula desceu
float vaoParado() { return BOCA_PARADA + 0.07 * u_dentes; }          // a abertura parada (maior com os dentes maiores)
// o lábio de cima repuxa nas sílabas fortes e no alerta, mais em cima das presas (o rosnado)
float repuxa(float x) {
  float onde = 0.35 * clamp(1.0 - sq(x / meiaDentes()), 0.0, 1.0) + exp(-sq((abs(x) - 0.20) / 0.13));
  return (0.040 * u_enfase + 0.050 * u_alerta) * onde;
}
// a mandíbula desce como uma peça só: os dentes da frente descem um pouco mais que os do canto (a
// dobradiça fica lá atrás), mas ninguém gira; nos cantos o lábio cobre os dentes que desceram
float quedaMand(float x) { return abreMand() * (0.55 + 0.45 * clamp(1.0 - sq(x / meiaDentes()), 0.0, 1.0)); }
// a gengiva (a linha "de repouso", sem repuxar nem abrir): y de cima, y de baixo (parada), quanto falta
// para o canto e a inclinação da linha de cima. É nela que nascem os dentes.
vec4 linhaRepouso(float x) {
  float meia = meiaDentes();
  float canto = BOCA_CANTO - 0.05 * u_feliz + 0.05 * u_torto;
  float f = clamp(1.0 - sq(x / meia), 0.0, 1.0);
  float amp = BOCA_AMP + 0.05 * u_feliz - 0.13 * u_torto;
  float cima = canto + amp * pow(f, 0.85) + u_torto * 0.035 * sin(x * 19.0 + u_t * 3.0);
  float incl = amp * 0.85 * pow(max(f, 0.04), -0.15) * (-2.0 * x / (meia * meia));
  return vec4(cima, cima + vaoParado() * pow(f, 0.6), f, incl);
}
// os LÁBIOS: a abertura de verdade neste x (y de cima, y de baixo, quanto falta para o canto, inclinação de
// cima). Abrem com a mandíbula (mais no meio; os cantos ficam presos), o de cima repuxa e os cantos esticam.
vec4 linhaDaBoca(float x) {
  float meia = meiaDentes() + 0.025 * u_boca;
  float canto = BOCA_CANTO - 0.05 * u_feliz + 0.05 * u_torto;
  float f = clamp(1.0 - sq(x / meia), 0.0, 1.0);
  float amp = BOCA_AMP + 0.05 * u_feliz - 0.13 * u_torto;
  float cima = canto + amp * pow(f, 0.85) + u_torto * 0.035 * sin(x * 19.0 + u_t * 3.0) - repuxa(x)
             - GENGIVA_VISTA * pow(f, 0.5) * (0.80 + 0.40 * vn(vec2(x * 11.0, 3.0)));   // lábio repuxado: a gengiva aparece
  float vao = (vaoParado() + abreMand()) * pow(f, 0.6) + repuxa(x)
            + GENGIVA_VISTA * pow(f, 0.5) * (1.60 + 0.40 * vn(vec2(x * 11.0, 3.0)) + 0.40 * vn(vec2(x * 13.0, 9.0)));
  float incl = amp * 0.85 * pow(max(f, 0.04), -0.15) * (-2.0 * x / (meia * meia));
  return vec4(cima, cima + vao, f, incl);
}


vec3 virar(vec3 n) {
  vec2 a = u_giro * vec2(0.50, 0.40);
  float cy = cos(a.x), sy = sin(a.x), cp = cos(a.y), sp = sin(a.y);
  n = vec3(n.x * cy + n.z * sy, n.y, -n.x * sy + n.z * cy);
  return vec3(n.x, n.y * cp + n.z * sp, -n.y * sp + n.z * cp);
}


// a meia largura da cabeça numa altura y (0 no meio do rosto, positivo para baixo): a mesma conta da silhueta
// em cabeca(); e quanto a parte de baixo do rosto fica à frente do eixo do pescoço (o queixo é o que mais
// anda para o lado quando ele vira)
float meiaLargura(float y) {
  float largo = y < 0.0 ? 0.66 : 0.66 - 0.34 * pow(clamp(y, 0.0, 1.0), 1.25);
  float altura = y < 0.0 ? 0.78 : 0.84 + 0.09 * u_boca;
  return largo * sqrt(max(1.0 - sq(y / altura), 0.0));
}
float avanco(float y) { return 0.24 * deg(0.0, 0.80, y); }

// ================================================================== a cabeça v2 (a partir da referência do dono)
// Construída como na referência: um bulbo liso no meio da testa que afina até virar crista entre os olhos;
// faixas largas de matéria que nascem entre os olhos e sobem em leque, uma por cima da outra, até os lobos
// das têmporas (que fazem a silhueta); faixas descendo pelas maçãs; uma mandíbula estreita em V até o queixo.
// Cada faixa é uma tira arredondada ao longo de uma curva (Bézier), pintada de trás para a frente com sombra
// de contato na de baixo, e iluminada como matéria negra molhada. Cores medidas na imagem.
const vec3 PELE_ESCURA = vec3(0.004, 0.004, 0.043);
const vec3 PELE_MEIA = vec3(0.027, 0.031, 0.094);
const vec3 REFLEXO = vec3(0.835, 0.851, 0.988);
const vec3 BRILHO_VIOLETA = vec3(0.322, 0.125, 0.592);
float dot2(vec2 v) { return dot(v, v); }
// a superfície molhada não é lisa: ondulações miúdas que espalham pontinhos de reflexo (duas oitavas)
vec2 micro;
vec2 ondulacao(vec2 p) {
  vec2 q = p * 15.0 + vec2(u_t * 0.15, 0.0);
  float n0 = vn(q), nx = vn(q + vec2(0.05, 0.0)), ny = vn(q + vec2(0.0, 0.05));
  vec2 q2 = p * 41.0 + 7.0;
  float m0 = vn(q2), mx = vn(q2 + vec2(0.05, 0.0)), my = vn(q2 + vec2(0.0, 0.05));
  return vec2(nx - n0, ny - n0) * 5.0 + vec2(mx - m0, my - m0) * 2.5;
}

// distância com sinal até uma Bézier quadrática A->B->C (x) e a posição ao longo dela, de 0 a 1 (y)
// (a conta exata de Inigo Quilez, devolvendo também o t e o lado)
vec2 bezier(vec2 pos, vec2 A, vec2 B, vec2 C) {
  vec2 a = B - A;
  vec2 b = A - 2.0 * B + C;
  vec2 c = a * 2.0;
  vec2 d = A - pos;
  float kk = 1.0 / max(dot(b, b), 1e-6);
  float kx = kk * dot(a, b);
  float ky = kk * (2.0 * dot(a, a) + dot(d, b)) / 3.0;
  float kz = kk * dot(d, a);
  float p = ky - kx * kx;
  float q = kx * (2.0 * kx * kx - 3.0 * ky) + kz;
  float h = q * q + 4.0 * p * p * p;
  float t;
  if (h >= 0.0) {
    h = sqrt(h);
    vec2 x = (vec2(h, -h) - q) / 2.0;
    vec2 uv = sign(x) * pow(abs(x), vec2(1.0 / 3.0));
    t = clamp(uv.x + uv.y - kx, 0.0, 1.0);
  } else {
    float z = sqrt(-p);
    float v = acos(clamp(q / (p * z * 2.0), -1.0, 1.0)) / 3.0;
    float m = cos(v);
    float n = sin(v) * 1.732050808;
    vec2 tt = clamp(vec2(m + m, -n - m) * z - kx, 0.0, 1.0);
    t = dot2(d + (c + b * tt.x) * tt.x) < dot2(d + (c + b * tt.y) * tt.y) ? tt.x : tt.y;
  }
  vec2 r = pos - (A + (c + b * t) * t);
  vec2 tg = c + 2.0 * b * t;
  return vec2(length(r) * (tg.x * r.y - tg.y * r.x < 0.0 ? -1.0 : 1.0), t);
}

// a matéria negra molhada: azul-marinho quase preto, reflexo estreito branco-azulado, reflexo largo azul,
// a beirada pega o azul do ambiente; recorte violeta de baixo/direita e azul da esquerda
vec3 materia(vec3 N, float ao) {
  N = normalize(N + vec3(micro * 0.35, 0.0));
  vec3 L = vec3(-0.4002, -0.7805, 0.4803);
  vec3 Hh = vec3(-0.2326, -0.4535, 0.8605);                            // a luz principal (de cima, à esquerda)
  vec3 Ht = normalize(vec3(0.10, -0.75, 1.0));                          // uma janela larga lá em cima
  float nh = max(dot(N, Hh), 0.0), nt = max(dot(N, Ht), 0.0);
  float nl = max(dot(N, L), 0.0);
  vec3 c = PELE_ESCURA * 0.6 + (PELE_MEIA - PELE_ESCURA) * nl * 0.35;   // preto quase absoluto
  c += REFLEXO * pow(nh, 140.0) * 1.7;                                 // reflexos estreitos e fortes
  c += REFLEXO * pow(nt, 55.0) * 0.55;                                 // o reflexo largo da janela, no alto das formas
  c += vec3(0.25, 0.30, 0.85) * pow(nh, 26.0) * 0.08;
  float fr = pow(1.0 - clamp(N.z, 0.0, 1.0), 2.5);
  float lat = pow(max(dot(N, vec3(0.62, 0.62, 0.48)), 0.0), 6.0);
  float laz = pow(max(dot(N, vec3(-0.88, -0.10, 0.46)), 0.0), 6.0);
  c += (BRILHO_VIOLETA * lat * 0.9 + vec3(0.15, 0.32, 1.0) * laz * 0.7) * fr;   // recortes só onde a forma vira
  return c * ao;
}

float silh;
// pinta uma faixa de matéria ao longo da curva A->B->C (larguras na base, no meio e na ponta)
void faixa(vec2 p, vec2 A, vec2 B, vec2 C, float w0, float w1, float w2) {
  // longe da faixa (fora da caixa dela, com folga para a sombra) não há nada a pintar: poupa a conta da curva
  float folga = max(max(w0, w1), w2) + 0.09;
  if (any(lessThan(p, min(min(A, B), C) - folga)) || any(greaterThan(p, max(max(A, B), C) + folga))) return;
  vec2 bt = bezier(p, A, B, C);
  float t = bt.y;
  float w = mix(mix(w0, w1, deg(0.0, 0.5, t)), w2, deg(0.5, 1.0, t));
  float d = abs(bt.x);
  // a sombra de contato que a faixa joga em volta (no que já está pintado embaixo dela)
  float sombra = exp(-max(d - w, 0.0) / 0.016) * step(w, d) * 0.85;
  col *= 1.0 - sombra * alfa;
  float a = deg(w + 0.004, w - 0.003, d);
  if (a <= 0.0) return;
  float u = clamp(bt.x / w, -1.0, 1.0);
  vec2 tg = normalize(B - A + (A - 2.0 * B + C) * t * 2.0 + vec2(1e-5, 0.0));
  vec2 nperp = vec2(-tg.y, tg.x);
  vec3 N = normalize(vec3(nperp * u * 1.1 + normalize(p - vec2(0.0, -0.06)) * 0.25, sqrt(1.0 - u * u) * 0.8 + 0.10));
  N = virar(N);
  float ao = 0.35 + 0.65 * pow(1.0 - u * u, 0.5);
  por(materia(N, ao), a);
  silh = max(silh, a);
}

// o contorno da cabeça (medido na referência): o raio em cada direção a partir de (0, -0.06)
float contorno(float a) {
  float r = 0.7136 - 0.1226 * cos(a) + 0.0112 * sin(a) + 0.1041 * cos(2.0 * a) - 0.0043 * sin(2.0 * a)
          + 0.0433 * cos(3.0 * a) + 0.0019 * sin(3.0 * a) + 0.0147 * cos(4.0 * a) + 0.0033 * sin(4.0 * a)
          + 0.0197 * cos(5.0 * a) - 0.0009 * sin(5.0 * a) + 0.0113 * cos(6.0 * a) + 0.0078 * cos(7.0 * a);
  r += 0.06 * exp(-a * a / 0.02);                                  // o queixo pontudo
  r += 0.09 * u_boca * exp(-a * a / 0.35);                         // a boca abre: o queixo desce
  return r;
}

void cabeca(vec2 P0, vec2 Pf, vec2 torce, vec3 fogo) {
  silh = 0.0;
  vec2 p = Pf + 0.010 * torce;
  float tb = u_t;
#ifdef LEVE
  micro = vec2(0.0);                                               // leve: sem os pontinhos de reflexo
#else
  micro = ondulacao(p);
#endif
  // ---- a massa de base: a silhueta inteira, abaulada
  vec2 q = p - vec2(0.0, -0.06);
  float ang = atan(q.x, q.y);
  float R = contorno(ang);
  float rq = length(q);
  float dB = R - rq;                                               // + dentro
  float base = deg(-0.004, 0.004, dB);
  silh = max(silh, base);
  // a aura: fumaça violeta (cores do fundo da referência) e o brilho que vaza da beirada
  float fora = max(-dB, 0.0);
#ifdef LEVE
  float fum = fbm3(vec2(p.x * 2.2, p.y * 1.6 + tb * 0.25) + 5.0);
#else
  float fum = fbm(vec2(p.x * 2.2, p.y * 1.6 + tb * 0.25) + 5.0);
#endif
  float aura = exp(-fora / 0.20) * deg(0.35, 0.80, fum);
  luz(vec3(0.15, 0.08, 0.42), aura * 0.55);
  vec2 sai = q / max(rq, 0.001);
  float lado_d = deg(-0.2, 0.9, sai.x), lado_e = deg(-0.2, 0.9, -sai.x);
  luz(vec3(0.20, 0.35, 1.00), exp(-fora / 0.025) * 0.55 * (0.4 + 0.6 * lado_e) * step(0.0, -dB + 0.001));
  luz(BRILHO_VIOLETA, exp(-fora / 0.030) * 0.55 * (0.3 + 0.7 * max(lado_d, deg(0.3, 0.9, sai.y))) * step(0.0, -dB + 0.001));
  if (base > 0.001) {
    float hb = sqrt(max(1.0 - sq(rq / R), 0.0));
    vec3 N0 = virar(normalize(vec3(sai * (1.0 - hb) * 1.4, hb + 0.15)));
    vec3 cb0 = materia(N0, 0.55 + 0.45 * hb);
    float beira = exp(-dB / 0.035);
    cb0 += vec3(0.15, 0.30, 1.0) * beira * (0.25 + 0.75 * lado_e) * 0.9 + BRILHO_VIOLETA * beira * lado_d * 0.9;
    por(cb0, base);
  }
  // ---- os lobos das têmporas (atrás), depois as faixas em leque, de fora para dentro
  float re = 0.006 * sin(tb * 1.3);                                // respira: as faixas incham um pouco
  float al = 1.0 - 0.07 * u_alerta;                                // em alerta, a matéria se contrai
  faixa(p, vec2(-0.56, -0.28), vec2(-0.60, -0.60), vec2(-0.36, -0.80), 0.06, 0.11 * al + re, 0.03);   // os lobos das têmporas, por dentro do contorno
  faixa(p, vec2(0.57, -0.28), vec2(0.61, -0.60), vec2(0.37, -0.81), 0.06, 0.11 * al + re, 0.03);
  faixa(p, vec2(-0.102, -0.059), vec2(-0.307, -0.199), vec2(-0.435, -0.506), 0.025, 0.075 * al + re, 0.07);
  faixa(p, vec2(0.102, -0.059), vec2(0.307, -0.199), vec2(0.435, -0.506), 0.025, 0.075 * al + re, 0.07);
  faixa(p, vec2(-0.038, -0.033), vec2(-0.230, -0.327), vec2(-0.320, -0.698), 0.02, 0.07 * al + re, 0.09);
  faixa(p, vec2(0.038, -0.033), vec2(0.230, -0.327), vec2(0.320, -0.711), 0.02, 0.07 * al + re, 0.09);
  // ---- o bulbo do meio da testa: largo em cima, afinando até a crista entre os olhos
  float yb = p.y;
  float hw = 0.34 * pow(clamp((0.02 - yb) / 0.82, 0.0, 1.2), 0.85) * (1.0 - 0.35 * deg(-0.70, -0.98, yb));
  float topo = deg(-0.99, -0.86, yb);
  float ub = p.x / max(hw, 0.002);
  float ab = deg(1.0 + 0.006 / max(hw, 0.01), 1.0 - 0.006 / max(hw, 0.01), abs(ub)) * step(yb, 0.02) * topo;
  col *= 1.0 - exp(-max(abs(ub) - 1.0, 0.0) * hw / 0.025) * step(1.0, abs(ub)) * 0.6 * alfa * step(yb, 0.0) * topo;
  if (ab > 0.0) {
    float uu = clamp(ub, -1.0, 1.0);
    vec3 N = virar(normalize(vec3(uu * 0.9, -0.25 * deg(-0.4, 0.0, yb), sqrt(1.0 - uu * uu) + 0.15)));
    vec3 cb = materia(N, 0.6 + 0.4 * (1.0 - uu * uu));
    float mancha = deg(0.42, 0.62, fbm3(p * 7.0 + 3.0));                       // o reflexo molhado é irregular
    cb += REFLEXO * exp(-sq((uu + 0.10) / 0.16) - sq((yb + 0.55) / 0.20)) * (0.35 + 0.75 * mancha);  // o reflexo no alto da testa
    cb += REFLEXO * exp(-sq((uu - 0.35) / 0.05) - sq((yb + 0.30) / 0.10)) * 0.25;
    por(cb, ab);
  }
  // ---- embaixo dos olhos: faixas descendo pelas maçãs; o focinho em V até o lábio
  float bx = 0.80 * abreMand();
  faixa(p, vec2(-0.13, 0.05), vec2(-0.36, 0.06), vec2(-0.52, 0.02), 0.03, 0.05, 0.035);
  faixa(p, vec2(0.13, 0.05), vec2(0.36, 0.06), vec2(0.52, 0.02), 0.03, 0.05, 0.035);
  faixa(p, vec2(-0.02, 0.0), vec2(-0.07, 0.16), vec2(-0.15, 0.30), 0.02, 0.045, 0.03);
  faixa(p, vec2(0.02, 0.0), vec2(0.07, 0.16), vec2(0.15, 0.30), 0.02, 0.045, 0.03);
  // ---- a mandíbula: faixas dos cantos da boca até o queixo, e o bulbo do queixo
  faixa(p, vec2(-0.44, 0.22), vec2(-0.30, 0.56 + bx), vec2(-0.05, 0.74 + bx), 0.04, 0.05, 0.03);
  faixa(p, vec2(0.44, 0.22), vec2(0.30, 0.56 + bx), vec2(0.05, 0.74 + bx), 0.04, 0.05, 0.03);
  faixa(p, vec2(0.0, 0.56 + bx), vec2(0.004, 0.66 + bx), vec2(0.008, 0.80 + bx), 0.05, 0.045, 0.012);
  // ---- arcos elétricos perto dos olhos e na beirada (piscam)
  float arco = abs(fbm3(p * vec2(9.0, 7.0) + vec2(tb * 0.6, -tb * 0.4)) - 0.5);
  float onde = exp(-sq((abs(p.x) - 0.66) / 0.14) - sq((p.y + 0.28) / 0.26)) * 1.4 + exp(-fora / 0.08) * 0.7 * (1.0 - base);
  vec3 eletrico = mix(vec3(0.45, 0.68, 1.0), LARANJA, u_alerta);
  luz(eletrico, exp(-sq(arco / 0.014)) * onde * (0.6 + 0.4 * sin(tb * 13.0 + p.y * 9.0)));
  luz(eletrico * 0.6, exp(-sq((abs(p.x) - 0.70) / 0.12) - sq((p.y + 0.25) / 0.20)) * 0.35 * u_olho * u_brilho);   // o brilho dos olhos vaza pelos lados
  pele = max(base, silh);
}

// um olho: lâmina rasgada, barriguda embaixo, com a beirada de cima em chama.
// Fica dentro de uma órbita: a beirada da órbita é escura, o branco mora no fundo da barriga
// e a parte de cima fica na sombra da sobrancelha; o brilho escapa mais para baixo do que para cima.
void olho(vec2 P, float lado, float abertura, float tam, vec3 cor, vec2 torce) {
  vec2 c = vec2(lado * OLHO_X, OLHO_Y + 0.03 * u_inclina);
  float ang = radians(OLHO_ANG + 13.0 * u_inclina);
  vec2 r = vec2((P.x - c.x) * lado, P.y - c.y) + 0.02 * torce;
  float u = r.x * cos(ang) - r.y * sin(ang);
  float v = r.x * sin(ang) + r.y * cos(ang);
  float meia = OLHO_MEIA * tam;
  float perfil = pow(clamp(1.0 - sq(u / meia), 0.0, 1.0), 0.75);
  float barriga = (0.5 + 0.5 * clamp(u / meia, -1.0, 1.0)) * 0.35 + 0.65;
  float baixo = OLHO_BAIXO * abertura * tam * perfil * barriga * (1.0 - 0.62 * u_feliz);
  float chama = (fbm3(vec2(u * 7.0, v * 4.0 + u_t * 1.7) + lado * 13.0) - 0.35) * 0.09 * clamp(u / meia + 0.4, 0.0, 1.4);
  float cima = OLHO_CIMA * abertura * tam * perfil * (1.0 + 1.1 * u_feliz) + chama * abertura * (1.0 - 0.45 * u_feliz);
  float d = v > 0.0 ? v - baixo : -v - cima;
  if (abs(u) >= meia) d = length(vec2(abs(u) - meia, v));
  // a pálpebra: desce de cima e cobre o olho (na piscada); a beirada dela pega a luz do olho
  float palp = clamp(u_palpebra, 0.0, 1.0);
  float semPalpebra = d;
  float beira = -cima + palp * (cima + baixo + 0.012);
  d = max(d, beira - v);
  float fora = max(d, 0.0);
  float aceso = min(1.0, abertura + 0.2) * (1.0 - 0.7 * palp) * u_brilho;
  // a beirada da órbita, colada no olho, no escuro: é ela que afunda o olho na cabeça
  por(vec3(0.003, 0.002, 0.010), deg(0.045, 0.010, d) * 0.80 * pele * deg(0.02, 0.25, abertura));
  // o brilho que escapa: curto e forte na beirada; o largo é fraco e cai mais para baixo (a sobrancelha segura o de cima)
  float paraBaixo = 0.35 + 0.65 * deg(-0.05, 0.07, v);
  luz(cor, exp(-fora / 0.15) * 0.22 * abertura * paraBaixo * (1.0 - palp) * u_brilho);
  luz(cor, exp(-fora / 0.022) * 0.80 * aceso * (0.45 + 0.55 * paraBaixo) * (0.85 + 0.25 * deg(0.0, meia, u)));
  luz(cor, exp(-sq((v - beira) / 0.007)) * deg(0.004, -0.010, semPalpebra) * palp * (1.0 - palp) * 2.4);
  // por dentro: energia correndo devagar ao longo do olho; a faixa de cima, sob a pálpebra, fica azul;
  // embaixo, na barriga, um fio de luz quase branca; perto da beirada o branco vira azul elétrico
  float vn = clamp((v + cima) / max(cima + baixo, 0.01), 0.0, 1.0);   // 0 em cima, 1 embaixo
  float energia = fbm3(vec2(u * 5.0 - u_t * 0.55 * lado, v * 9.0 + u_t * 0.2) + lado * 7.0);
  float miolo = deg(0.0, -0.030, d) * deg(0.04, 0.50, vn);
  // o olhar: o ponto mais branco anda dentro do olho, para o lado em que ele olha
  miolo *= 0.62 + 0.38 * exp(-(sq((u - u_olhar.x * lado * 0.13) / 0.17) + sq((v - 0.035 - u_olhar.y * 0.035) / 0.075)));
  miolo *= 0.82 + 0.36 * energia;
  vec3 dentroCor = mix(cor * (0.70 + 0.35 * energia), vec3(1.0), clamp(miolo, 0.0, 1.0));
  dentroCor += vec3(0.22, 0.27, 0.32) * exp(-sq((vn - 0.74) / 0.11)) * deg(0.0, -0.025, d);
  // o reflexo molhado da superfície do olho: em cima e à esquerda nos dois (a luz principal vem dali)
  dentroCor += vec3(0.80, 0.90, 1.0) * exp(-(sq((u + 0.11 * lado) / 0.045) + sq((vn - 0.24) / 0.07))) * 0.55 * (1.0 - palp);
  por(min(dentroCor, vec3(1.0)), deg(0.010, -0.010, d));
  float treme = 0.7 + 0.3 * sin(u_t * 9.0 + lado * 2.0);
  float rastro = exp(-sq((v + 0.035 + 0.12 * (u - meia)) / 0.022)) * deg(meia - 0.05, meia + 0.02, u) * deg(meia + 0.26 * treme, meia + 0.04, u);
  luz(cor, rastro * 0.8 * abertura * (1.0 - palp) * u_brilho);
}

// ================================================================== a boca v2 (a partir da referência do dono)
// Como na referência: um sorriso largo de canto a canto com duas fileiras de presas cônicas e grossas (cor de
// osso, raiz escura, ponta afiada que pende para o meio), as de baixo encaixando entre as de cima; a gengiva
// violeta e molhada abraçando cada presa; o fundo escuro aceso por uma LUZ PONTUAL violeta lá dentro (a
// garganta), que acende a gengiva, atravessa a beirada fina das presas e reflete nos lábios; os lábios são a
// mesma matéria negra molhada da cabeça. As presas ficam num ARCO (a arcada): as do meio de frente, as dos
// cantos virando de lado, mais juntas e mais para o fundo, como numa boca de verdade.
const vec3 OSSO_CLARO = vec3(0.92, 0.80, 0.62);              // (medidas nas presas da referência)
const vec3 OSSO_RAIZ = vec3(0.30, 0.19, 0.14);
const vec3 CARNE = vec3(0.38, 0.16, 0.60);                   // a gengiva
const vec3 CARNE_FUNDA = vec3(0.060, 0.018, 0.100);
const vec3 FUNDO_BOCA = vec3(0.050, 0.014, 0.085);
const vec3 LUZ_GARGANTA = vec3(0.66, 0.24, 1.00);
const float ARCO_MAX = 1.40;                                  // até onde a arcada vira nos cantos (radianos)
const float AA_BOCA = 0.0032;
vec3 luzBoca;                                                 // a luz pontual lá dentro (z negativo = para o fundo)
float forcaLuzBoca;

// quanto da luz pontual da garganta chega num ponto (x, y, z) com a normal N: difusa, caindo com a distância
float luzPontual(vec3 pos, vec3 N) {
  vec3 d = luzBoca - pos;
  return forcaLuzBoca * max(dot(N, normalize(d)), 0.0) / (1.0 + dot(d, d) / 0.012);
}

// uma presa: um cone grosso de osso. raiz (escondida na gengiva), dir (para a ponta), comprimento, meia
// largura na base, curva (quanto a ponta pende para o lado), giro (o ângulo dela na arcada: as dos cantos
// estão viradas de lado), escuro (as do fundo pegam menos luz)
void presa(vec2 p, vec2 raiz, vec2 dir, float L, float wb, float curva, float giro, float escuro, float vis, float semente) {
  vec2 lado = vec2(dir.y, -dir.x);
#ifndef LEVE
  // a sombra que ela joga no que está atrás (a luz vem de cima, da esquerda)
  vec2 qs = p - raiz - vec2(0.006, 0.009);
  float ts = dot(qs, dir) / L;
  float as1 = dot(qs, lado) - curva * ts * ts;
  float sombra = deg(0.010, -0.002, abs(as1) - wb * pow(max(1.0 - ts, 0.0), 1.1) * (1.0 + 0.9 * ts * (1.0 - ts))) * step(0.0, ts) * step(ts, 1.0);
  col *= 1.0 - sombra * 0.55 * vis;
#endif
  vec2 q = p - raiz;
  float t = dot(q, dir) / L;                                    // 0 na raiz, 1 na ponta
  if (t < -0.05 || t > 1.0) return;
  float a = dot(q, lado) - curva * t * t;                       // atravessado, já descontando a curva
  float w = wb * pow(1.0 - t, 1.1) * (1.0 + 0.9 * t * (1.0 - t));        // base cheia, ponta fina de espinho
  float corpo = deg(AA_BOCA, -AA_BOCA, abs(a) - w) * vis;
  if (corpo <= 0.0) return;
  // a normal do cone: redonda de um lado ao outro, olhando um pouco para a ponta (ele afina)
  float u = clamp(a / max(w, 0.0005), -1.0, 1.0);
  float nz = sqrt(max(1.0 - u * u, 0.0));
  vec3 Nl = normalize(vec3(u, 0.85 * wb / L * nz, nz));
  float cg = cos(giro), sg = sin(giro);
  Nl = vec3(Nl.x * cg + Nl.z * sg, Nl.y, -Nl.x * sg + Nl.z * cg);   // virada de lado na arcada
  vec3 N = normalize(vec3(lado * Nl.x + dir * Nl.y, Nl.z));
  vec3 Lk = normalize(vec3(-0.45, -0.55, 0.70));                // a luz principal: de cima, da esquerda
  float dif = clamp((dot(N, Lk) + 0.25) / 1.25, 0.0, 1.0);      // osso é um pouco translúcido: sombra macia
  // a cor: raiz escura, corpo de osso, ponta fina clareando; cada presa um tiquinho diferente, com estrias
  vec3 alb = mix(OSSO_RAIZ, OSSO_CLARO, deg(0.0, 0.45, t)) * (0.90 + 0.10 * rnd(semente));
  alb = mix(alb, vec3(0.95, 0.90, 0.82), deg(0.70, 1.0, t) * 0.30);
  alb *= 0.93 + 0.07 * sin(u * 14.0 + semente * 9.0) * vn(vec2(semente * 5.0, t * 6.0));
  vec3 c = alb * (0.025 + 1.10 * dif * dif) + vec3(0.020, 0.010, 0.030);
  // o brilho molhado: um ponto forte e uma faixa larga e fraca, do lado da luz
  vec3 H = normalize(Lk + vec3(0.0, 0.0, 1.0));
  float nh = max(dot(N, H), 0.0);
  c += vec3(0.95, 0.94, 1.0) * (pow(nh, 70.0) * 0.85 + pow(nh, 12.0) * 0.07);
  // a luz da garganta por trás atravessa a beirada e a ponta, onde ela é fina
  c += LUZ_GARGANTA * forcaLuzBoca * (pow(1.0 - Nl.z, 2.0) + deg(0.6, 1.0, t) * 0.4) * 0.12;
  c *= 0.30 + 0.70 * deg(-0.05, 0.30, t);                        // a raiz some na gengiva
  por(min(c * escuro, vec3(1.0)), corpo);
}

// uma fileira na arcada: n presas de canto a canto. sinal 1 = de cima (pendem), -1 = de baixo (sobem);
// desloc: meia presa na de baixo, para encaixar entre as de cima; tamL: o comprimento (fração do vão)
void fileiraV2(vec2 p, float n, float larg, float sinal, float desloc, float semente, float tamL, float escala,
               float escuro, float recuo, float presaK, float vis) {
  float M = meiaDentes() * larg;
  float passo = 2.0 * ARCO_MAX / n;
  float fi = asin(clamp(p.x / M, -0.999, 0.999));
  float k0 = floor((fi + ARCO_MAX) / passo - desloc);
  float s = p.x < 0.0 ? -1.0 : 1.0;
#ifdef LEVE
  for (int i = 1; i < 2; i++) {                                 // leve: só a presa deste ponto
#else
  for (int i = 0; i < 3; i++) {
#endif
    float k = k0 + s * (1.0 - float(i));                         // de fora para dentro: a da frente por último
    if (k < 0.0 || k > n - 1.0) continue;
    float fk = -ARCO_MAX + (k + 0.5 + desloc) * passo + (rnd(k + semente) - 0.5) * 0.18 * passo;
    if (abs(fk) > ARCO_MAX) continue;
    float xk = M * sin(fk);
    float frente = cos(fk);                                      // 1 no meio; nos cantos ela está virada de lado
    float perto = mix(0.62, 1.0, frente);                        // e mais para o fundo: parece menor
    vec4 lr = linhaRepouso(xk);
    vec4 lr2 = linhaRepouso(xk + 0.004);
    float yg = sinal > 0.0 ? lr.x : lr.y + quedaMand(xk);
    float yg2 = sinal > 0.0 ? lr2.x : lr2.y + quedaMand(xk + 0.004);
    vec2 dir = normalize(vec2(-(yg2 - yg) / 0.004 * 0.55, 1.0)) * sinal;   // em leque, seguindo a curva da boca
    float vao = max(lr.y - lr.x, 0.0);
    float presaF = step(abs(abs(k + 0.5 + desloc - n * 0.5) - presaK), 0.5);   // as presas maiores
    float L = max(vao * tamL * (0.80 + 0.40 * rnd(k + semente + 3.0)) * (1.0 + 0.28 * presaF), 0.016)
            * perto * escala * (1.0 + 0.30 * u_dentes);
    float wb = M * passo * 0.46 * mix(0.75, 1.0, frente) * (0.90 + 0.20 * rnd(k + semente + 7.0))
             * (1.0 + 0.12 * presaF) * escala * (1.0 + 0.10 * u_dentes);
    // a ponta pende para o meio da boca (mais nas de fora), e cada uma um pouco diferente
    float curva = (-sign(xk) * sinal * (0.60 + 0.70 * rnd(k + semente + 11.0)) * deg(0.0, 0.10, abs(xk))
                   + (rnd(k + semente + 13.0) - 0.5) * 0.40) * wb * (sinal > 0.0 ? 1.0 : 0.45);   // as de baixo quase retas
    presa(p, vec2(xk, yg) + dir * (recuo - 0.004), dir, L, wb, curva, fk, escuro * mix(0.55, 1.0, frente), vis, k + semente);
  }
}

// a gengiva: carne violeta e molhada rente às raízes, abraçando cada presa (desce entre elas); a beirada,
// que olha para dentro da boca, pega a luz da garganta. "exposta": quanto dela o lábio deixa ver
void gengivaV2(vec2 p, float linha, float sinal, float n, float larg, float desloc, float vis, float exposta) {
  float M = meiaDentes() * larg;
  float passo = 2.0 * ARCO_MAX / n;
  float fi = asin(clamp(p.x / M, -0.999, 0.999));
  float fr = fract((fi + ARCO_MAX) / passo - desloc);
  float arco = 1.0 - sq(2.0 * fr - 1.0);                         // 1 no meio de cada presa, 0 entre elas
  float prof = (0.010 + 0.018 * (1.0 - arco)) * mix(0.6, 1.0, cos(fi));
  float dentro = (p.y - linha) * sinal;                          // 0 na linha, crescendo para a ponta das presas
  float topo = -exposta - 0.005;
  float g = deg(prof + 0.003, prof - 0.003, dentro) * deg(topo - 0.003, topo + 0.003, dentro) * vis;
  if (g <= 0.0) return;
  float s = clamp((dentro - topo) / max(prof - topo, 0.002), 0.0, 1.0);   // 0 junto do lábio, 1 na beirada
  vec3 N = virar(normalize(vec3(0.0, sinal * (s * 2.0 - 1.0) * 0.9, 0.55)));   // roliça
  float lp = luzPontual(vec3(p, -0.015), N);
  float manchas = 0.82 + 0.18 * vn(vec2(p.x * 60.0, dentro * 90.0 + sinal * 5.0));
  vec3 c = CARNE_FUNDA + CARNE * (0.30 + 2.2 * lp) * manchas;
  // molhada: brilha em pontinhos, onde ela vira para a luz de cima
  float gotas = deg(0.62, 0.85, vn(vec2(p.x * 30.0, sinal * 11.0)));
  c += vec3(0.85, 0.75, 1.0) * gotas * pow(max(dot(N, normalize(vec3(-0.3, -0.6, 0.75))), 0.0), 6.0) * 0.30;
  c *= 0.25 + 0.75 * deg(0.0, 0.55, s);                          // escurece junto do lábio: acesa só na beirada
  c *= 0.85 + 0.15 * sin(p.x * 95.0 + vn(vec2(p.x * 12.0, 3.0)) * 4.0) * deg(0.6, 0.2, s);   // dobras na carne exposta
  c += vec3(0.50, 0.24, 0.80) * exp(-sq((prof - dentro) / 0.0035)) * (0.25 + 0.50 * forcaLuzBoca);   // o fio aceso na raiz
  por(c, g);
}

// a boca: o rasgo de canto a canto (as mesmas linhas que já abrem com a fala, repuxam no alerta etc.)
void bocaV2(vec2 P, vec2 torce) {
  float x = P.x + 0.010 * torce.x, y = P.y + 0.010 * torce.y;
  vec2 p = vec2(x, y);
  vec4 lb = linhaDaBoca(x);
  vec4 lb2 = linhaDaBoca(x + 0.004);
  vec4 lr = linhaRepouso(x);
  float meia = meiaDentes() + 0.025 * u_boca;
  float canto = BOCA_CANTO - 0.05 * u_feliz + 0.05 * u_torto;
  float cima = lb.x, baixo = lb.y, vao = baixo - cima;
  float sU = (lb2.x - lb.x) / 0.004, sL = (lb2.y - lb.y) / 0.004;
  float dU = (cima - y) / sqrt(1.0 + sU * sU);                   // + acima do lábio de cima
  float dL = (y - baixo) / sqrt(1.0 + sL * sL);                  // + abaixo do lábio de baixo
  float d = abs(x) < meia ? max(dU, dL) : length(vec2(abs(x) - meia, y - canto));
  if (d > 0.30) return;
  // a luz pontual: lá dentro, no meio da boca e para o fundo; pulsa devagar e acende mais quando ele fala
  vec4 lc = linhaDaBoca(0.0);
  luzBoca = vec3(0.0, lc.x + (lc.y - lc.x) * 0.58, -0.10);
  forcaLuzBoca = (0.55 + 0.75 * u_boca + 0.25 * u_enfase + 0.20 * u_alerta) * (0.88 + 0.12 * vn(vec2(u_t * 1.3, 4.0)));
  float dentro = deg(AA_BOCA, -AA_BOCA, d);
  luz(LUZ_GARGANTA * 0.5, exp(-max(d, 0.0) / 0.035) * 0.05 * forcaLuzBoca * (1.0 - dentro));   // vaza pelo vão
  if (dentro > 0.0) {
    // o fundo: uma tigela escura (céu da boca em cima, chão embaixo), funda no meio, acesa pela garganta
    float fy = clamp((y - cima) / max(vao, 0.001), 0.0, 1.0);
    float fx = clamp(x / max(meia, 0.01), -1.0, 1.0);
    float z = -0.10 * sin(3.14159 * fy) * sqrt(max(1.0 - fx * fx, 0.0));
    vec3 N = normalize(vec3(-fx * 0.7, -(fy - 0.5) * 1.4, 1.0));
    float lp = luzPontual(vec3(x, y, z), N);
    float rugas = 0.5 + 0.5 * sin((fy * 7.0 + fx * fx * 2.5) * 6.2832 + vn(p * 30.0) * 2.0);
    vec3 c = FUNDO_BOCA * (0.7 + 0.3 * vn(p * 25.0));
    c += (LUZ_GARGANTA * 0.55 + CARNE * 0.45) * lp * (0.80 + 0.20 * rugas);
    c += vec3(0.85, 0.75, 1.0) * deg(0.62, 0.85, vn(p * 70.0)) * lp * 0.25;   // molhado: pontinhos de brilho
    float aberta = deg(0.25, 0.85, u_boca);
    c *= 1.0 - 0.75 * exp(-sq(x / 0.13) - sq((fy - 0.62) / 0.22)) * aberta;   // a garganta: um buraco escuro no fundo
    float ceu = (1.0 - deg(0.05, 0.40, fy)) * aberta;                      // o céu da boca: dobras em arco
    c += CARNE * lp * 0.35 * ceu * pow(max(sin((fy * 9.0 + fx * fx * 3.0) * 3.14159), 0.0), 3.0);
    c *= 0.35 + 0.65 * deg(0.0, 0.06, -d);                                 // escurece rente aos lábios
    por(c, dentro);
    float vis = deg(0.004, -0.004, d) * deg(0.010, 0.05, vao);
    float quedaX = lr.y + quedaMand(x);
    fileiraV2(p, 15.0, 0.90, -1.0, 0.5, 71.0, 0.57, 1.0, 0.92, 0.0, 2.0, vis);   // as de baixo (arcada mais estreita)
    gengivaV2(p, quedaX, -1.0, 15.0, 0.90, 0.5, vis, max(baixo - quedaX, 0.0));
    fileiraV2(p, 16.0, 0.96, 1.0, 0.0, 5.0, 0.52, 1.0, 1.0, 0.0, 3.0, vis);      // as de cima, na frente
    gengivaV2(p, lr.x, 1.0, 16.0, 0.96, 0.0, vis, max(lr.x - cima, 0.0));
    por(vec3(0.0, 0.0, 0.010), dentro * exp(-sq(max(-dU, 0.0) / 0.025)) * 0.40);   // a sombra do lábio de cima
  }
  // os lábios: a matéria negra da cabeça rolando para dentro da boca; a luz da garganta reflete na beirada
  float acima = step(y, (cima + baixo) * 0.5);
  float fora = acima > 0.5 ? dU : dL;
  float wl = mix(0.030, 0.042, 1.0 - acima) * (0.4 + 0.6 * deg(0.0, 0.25, lb.z));
  if (abs(x) < meia && fora > -AA_BOCA && fora < wl) {
    float s = clamp(fora / wl, 0.0, 1.0);
    float th = (1.0 - s) * mix(0.95, 1.35, acima);               // na beirada a superfície vira para dentro
    vec2 n2 = normalize(vec2(-(acima > 0.5 ? sU : sL), 1.0)) * (acima > 0.5 ? 1.0 : -1.0);
    vec3 N = virar(normalize(vec3(n2 * sin(th), cos(th))));
    vec3 c = materia(N, 0.55 + 0.45 * s);
    c += LUZ_GARGANTA * luzPontual(vec3(p, 0.02), N) * 0.9;
    c += REFLEXO * exp(-sq((fora - 0.003) / 0.0025)) * (0.06 + 0.10 * acima) * deg(0.35, 0.70, fbm3(vec2(x * 14.0, acima * 5.0)));
    por(c, deg(wl, wl * 0.55, fora) * deg(-AA_BOCA, AA_BOCA, fora) * 0.92);
  }
  // os cantos: um vinco fundo subindo para as bochechas
  float ladoB = x < 0.0 ? -1.0 : 1.0;
  vec2 dirV = normalize(vec2(ladoB * 0.75, -0.66));
  vec2 qv = vec2(x - ladoB * meia, y - canto);
  float alV = clamp(dot(qv, dirV), 0.0, 0.06);
  float dV = length(qv - dirV * alV);
  float vaiV = 1.0 - alV / 0.06;
  por(vec3(0.0, 0.0, 0.006), exp(-sq(dV / 0.006)) * vaiV * 0.75);
  luz(BRILHO_VIOLETA, exp(-sq((dV - 0.009) / 0.004)) * vaiV * 0.25);
}



void main() {
#ifdef NO_APP
  vec2 uv = vec2(tex_coord0.x, 1.0 - tex_coord0.y);   // (no Kivy a textura vem de cabeça para baixo)
#else
  vec2 uv = gl_FragCoord.xy / u_res;
#endif
  vec2 P = vec2(uv.x * 2.0 - 1.0, 1.0 - uv.y * 2.0);            // y cresce para baixo
  P.y -= 0.015 * sin(u_t * 1.3);                                 // a cabeça respira
#ifdef NO_APP
  // subindo da poça (u_presenca de 0 a 1): começa toda abaixo dela, sobe, passa um tiquinho
  // do lugar e assenta; sumindo, o mesmo ao contrário
  float pr = clamp(u_presenca, 0.0, 1.0);
  vec2 Pchao = P;                                                // a poça fica parada
  float sobe = smoothstep(0.12, 0.80, pr);
  float pulo = sin(3.14159 * clamp((pr - 0.60) / 0.40, 0.0, 1.0));
  P.y -= 1.75 * (1.0 - sobe) - 0.05 * pulo;
#endif
  // o enquadramento da referência do dono: a cabeça inteira, do alto da testa ao queixo
  P = P * 1.20 + vec2(0.0, -0.02);
  // a cabeça de lado: gira no plano da tela, em volta do pescoço
  float cr = cos(u_rolar), sr = sin(u_rolar);
  P = vec2(cr * P.x + sr * (P.y - 0.25), -sr * P.x + cr * (P.y - 0.25) + 0.25);
  // virando de verdade (pedido do dono, 14/10/2026): cada fatia da cabeça é um círculo visto de cima e virar
  // gira a fatia, então as feições andam por cima da curva: o olho do lado de longe encolhe, o de perto cresce
  // e a lateral do crânio aparece; a parte de baixo do rosto (à frente do eixo do pescoço) também anda para o
  // lado. Pf = onde este ponto da tela fica no rosto visto de frente. Acenando, o meio do rosto anda mais.
  float th = u_giro.x * 0.50;                                    // (o mesmo ângulo que gira a luz em virar())
  float yr = P.y + 0.06;
  float W = max(meiaLargura(yr), 0.06);
  float s = (P.x - sin(th) * avanco(yr)) / W;
  float sc = clamp(s, -1.0, 1.0);
  float af = clamp(asin(sc) - th, -1.5708, 1.5708);
  vec2 qd = vec2(P.x / 0.66, yr / 0.80);
  vec2 Pf = vec2(W * (sin(af) + s - sc), P.y - u_giro.y * 0.16 * sqrt(max(1.0 - dot(qd, qd), 0.0)));
  col = vec3(0.0);
  alfa = 0.0;
  pele = 0.0;
  vec2 torce = vec2(fbm3(Pf * 2.6 + 7.0), fbm3(Pf * 2.6 + 19.0)) - 0.5;
  // quem escuta ganha um anel verde abrindo
#ifndef SEM_EXTRAS
  float raio = length(P - vec2(0.0, 0.02));
  for (int k = 0; k < 2; k++) {
    float f = fract(u_t * 0.9 + float(k) * 0.5);
    luz(VERDE, exp(-sq((raio - (0.80 + f * 0.17)) / 0.008)) * (1.0 - f) * 0.55 * u_escuta);
  }
#endif
  vec3 fogo = mix(AZUL, LARANJA, u_alerta);
  cabeca(P, Pf, torce, fogo);
#ifndef SEM_BOCA
  bocaV2(Pf, torce);
#endif
#ifndef SEM_OLHOS
  olho(Pf, -1.0, u_olho, 1.0, fogo, torce);
  olho(Pf, 1.0, u_olho, 1.0 - 0.38 * u_torto, fogo, torce);
#endif
#ifndef SEM_EXTRAS
  // brasas soltas subindo
  for (int i = 0; i < 9; i++) {
    float n = float(i);
    float vida = fract(u_t * 0.2 + n * 0.31);
    vec2 onde = vec2(sin(n * 12.9) * 0.80 + 0.05 * sin(u_t + n), 0.74 - vida * 1.6);
    vec2 q = P - onde;
    luz(mod(n, 2.0) < 1.0 ? ROXO : AZUL, exp(-dot(q, q) / (0.00010 * (1.0 + 2.0 * (1.0 - vida)))) * sin(vida * 3.14159) * 0.75);
  }
#endif
  // nunca um quadrado em volta dele: tudo some até ZERO antes da beirada do retângulo onde ele é
  // pintado (a aura e o anel de quem escuta chegavam a 14% na borda), e a névoa fraquinha que
  // sobra longe da cabeça vira transparente de vez
  vec2 q4 = abs(uv * 2.0 - 1.0);
  q4 *= q4;
  float r4 = sqrt(sqrt(dot(q4, q4)));                       // contorno de cantos redondos
  float beira = 1.0 - r4;
  float semBeira = smoothstep(0.0, 0.13, beira);
  float semQuadro = semBeira * smoothstep(0.004, 0.02, alfa);
  col *= semQuadro;
  alfa *= semQuadro;
#ifdef NO_APP
  // a poça de sombra de onde ele sobe (e para onde volta): abre, ele passa, fecha
  float abre = smoothstep(0.0, 0.20, pr) * (1.0 - smoothstep(0.82, 1.0, pr));
  float linha = mix(1.30, 0.70, abre);                 // a superfície: o que está abaixo dela não aparece
  float onda = (fbm3(vec2(Pchao.x * 4.0, u_t * 1.5)) - 0.5) * 0.05;
  float acima = smoothstep(linha + 0.015, linha - 0.03, Pchao.y + onda);
  // o que acabou de sair ainda vem coberto de sombra
  float escuro = 1.0 - 0.8 * smoothstep(linha - 0.45, linha, Pchao.y) * abre;
  col *= acima * escuro;
  alfa *= acima;
  // a poça: elipse escura, borda roxa ondulando e fiapos de sombra subindo dela
  float temPoca = smoothstep(0.0, 0.05, abre);
  vec2 el = vec2(Pchao.x / (0.74 * abre + 0.001), (Pchao.y - 0.70) / (0.085 * abre + 0.001));
  float dp = length(el) + (fbm3(Pchao * 5.0 + u_t * 0.8) - 0.5) * 0.35;
  float poca = smoothstep(1.0, 0.80, dp) * temPoca;
  float aro = exp(-sq((dp - 0.95) / 0.07)) * temPoca;
  float subindo = clamp((linha - Pchao.y) / 0.5, 0.0, 1.0);
  float fiapo = smoothstep(0.55, 0.80, fbm3(vec2(Pchao.x * 3.0, Pchao.y * 2.0 + u_t * 1.4)))
                * (1.0 - subindo) * smoothstep(linha + 0.01, linha - 0.02, Pchao.y)
                * smoothstep(0.78, 0.35, abs(Pchao.x)) * abre;
  vec3 pcol = (vec3(0.012, 0.006, 0.030) * poca * 0.92 + ROXO * aro * 0.8 + vec3(0.03, 0.015, 0.07) * fiapo) * semBeira;
  float palfa = clamp(poca * 0.92 + aro * 0.6 + fiapo * 0.6, 0.0, 1.0) * semBeira;
  col += pcol * (1.0 - alfa);                          // ele passa NA FRENTE da poça
  alfa += palfa * (1.0 - alfa);
  // o Kivy mistura com a cor "pura": desfaz a multiplicação pela transparência
  gl_FragColor = vec4(min(col / max(alfa, 0.004), vec3(1.0)), alfa * min(pr * 8.0, 1.0));
#else
  gl_FragColor = vec4(col, alfa);
#endif
}
'''
