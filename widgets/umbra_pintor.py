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
uniform float u_lingua;                                // a língua saindo da boca (0 dentro, 1 toda para fora)
const vec3 AZUL = vec3(0.353, 0.627, 1.0);
const vec3 ROXO = vec3(0.608, 0.361, 1.0);
const vec3 LARANJA = vec3(1.0, 0.59, 0.2);
const vec3 VERDE = vec3(0.36, 1.0, 0.78);
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

// --- o relevo do rosto: uma superfície com altura. Cada "massa" é um calombo (ou uma cova, se
// negativa) e já soma, junto com a altura, a inclinação: é dela que a luz precisa. ---
vec3 relevo;      // x = altura; yz = quanto a altura cresce indo para a direita e para baixo
float pele;       // quanto deste ponto é cabeça (0 fora, 1 dentro): os olhos usam para não sujar o fundo
void massa(vec2 p, vec2 c, vec2 eixo, vec2 raio, float a) {
  vec2 q = p - c;
  vec2 l = vec2(dot(q, eixo), dot(q, vec2(-eixo.y, eixo.x))) / raio;
  float e = a * exp(-dot(l, l));
  vec2 g = -2.0 * e * l / raio;
  relevo += vec3(e, g.x * eixo.x - g.y * eixo.y, g.x * eixo.y + g.y * eixo.x);
}
// um rolete que acompanha uma curva y = yc(x) (os lábios): "incl" é quanto yc muda por unidade de x
void rolete(vec2 p, float yc, float incl, float w, float a) {
  float t = (p.y - yc) / w;
  float e = a * exp(-t * t);
  float gy = -2.0 * e * t / w;
  relevo += vec3(e, -gy * incl, gy);
}

// a linha da boca para um x: y de cima do vão, y de baixo, quanto falta para o canto (1 no meio, 0 no canto)
// e quanto a linha de cima inclina. A mesma conta desenha a boca e levanta os lábios no relevo.
vec4 linhaDaBoca(float x) {
  float meia = 0.50 + 0.03 * u_feliz;
  float canto = 0.20 - 0.05 * u_feliz + 0.05 * u_torto;
  float f = clamp(1.0 - sq(x / meia), 0.0, 1.0);
  float amp = 0.215 + 0.05 * u_feliz - 0.13 * u_torto;
  float cima = canto + amp * pow(f, 0.85) + u_torto * 0.035 * sin(x * 19.0 + u_t * 3.0) - 0.032 * u_enfase * pow(f, 0.6);
  float vao = (0.035 + 0.30 * u_boca) * pow(f, 0.6);
  float incl = amp * 0.85 * pow(max(f, 0.04), -0.15) * (-2.0 * x / (meia * meia));
  return vec4(cima, cima + vao, f, incl);
}

// a luz de um olho caindo na pele: o olho é uma faixa acesa um pouco acima da superfície
float luzDoOlho(vec2 P, vec3 N, float lado, vec2 eu, vec2 ev) {
  vec2 c = vec2(lado * (0.33 + 0.035 * ev.x), -0.19 + 0.03 * u_inclina + 0.035 * ev.y);
  vec2 e = vec2(lado * eu.x, eu.y);
  vec3 L = vec3(c + clamp(dot(P - c, e), -0.20, 0.27) * e - P, 0.085);
  float d2 = dot(L, L);
  return max(dot(N, L) * inversesqrt(d2), 0.0) * exp(-d2 / 0.022);
}

vec3 virar(vec3 n) {
  vec2 a = u_giro * vec2(0.50, 0.40);
  float cy = cos(a.x), sy = sin(a.x), cp = cos(a.y), sp = sin(a.y);
  n = vec3(n.x * cy + n.z * sy, n.y, -n.x * sy + n.z * cy);
  return vec3(n.x, n.y * cp + n.z * sp, -n.y * sp + n.z * cp);
}

// fios em relevo sob a pele: aparecem onde o ruído passa pela metade
float veio(vec2 q) { float n = fbm3(q); return pow(1.0 - abs(2.0 * n - 1.0), 10.0); }

// a cabeça: crânio largo que afina até o queixo; no alto se desfaz em labaredas que sobem.
// Por dentro é um relevo (testa, sobrancelhas, órbitas, maçãs, vincos, lábios, queixo) de pele negra e molhada,
// iluminado por uma luz fria de cima e da esquerda, um recorte violeta por trás à direita, um violeta por baixo
// e o azul dos olhos; nas beiradas a pele reflete o ambiente, como vidro escuro.
void cabeca(vec2 P0, vec2 Pf, vec2 torce, vec3 fogo) {
  vec2 P = P0 - u_giro * 0.04;      // a silhueta mal se mexe quando ele vira; o rosto (Pf) anda mais
  float y = P.y + 0.06;
  float alto = clamp(-y - 0.05, 0.0, 1.0);
  float lab = fbm(vec2(P.x * 2.6, P.y * 1.1 + u_t * 0.33) + 3.7);
  float forca = 0.06 + 0.95 * pow(alto, 1.25);
  float xx = P.x + 0.05 * torce.x;
  float largo = y < 0.0 ? 0.66 : 0.66 - 0.34 * pow(clamp(y, 0.0, 1.0), 1.25);
  float altura = y < 0.0 ? 0.78 : 0.84 + 0.09 * u_boca;       // o queixo desce com a boca
  vec2 qe = vec2(xx / largo, y / altura);
  float rr = length(qe);
  float d = rr - 1.0 + forca * (lab - 0.5);
  float fora = max(d, 0.0);
  // para onde a beirada aponta: o recorte só acende do lado da luz de trás e por baixo do queixo
  vec2 sai = normalize(vec2(qe.x / largo, qe.y / altura) + vec2(0.0, 0.0001));
  float recorte = deg(-0.30, 0.85, dot(sai, vec2(0.93, 0.37)));
  float porBaixo = deg(0.25, 0.95, dot(sai, vec2(-0.29, 0.957)));
  float borda = 0.07 + 0.93 * max(recorte, 0.6 * porBaixo);
  float chave = deg(0.15, 0.95, dot(sai, vec2(-0.75, -0.66)));   // a beirada do lado da luz principal: fria e fraca
  luz(ROXO, exp(-fora / 0.11) * 0.30 * step(-0.02, d) * (0.22 + 0.78 * borda));
  float perto = exp(-fora / 0.34) * step(0.0, d);
  float fiapo = fbm3(vec2(P.x * 3.0, P.y * 2.2 + u_t * 0.6) + 21.0);
  float solto = deg(0.50, 0.78, fiapo) * perto * (0.2 + 0.8 * clamp(-P.y + 0.4, 0.0, 1.0));
  por(vec3(0.078, 0.047, 0.227), solto * 0.85);
  luz(ROXO, solto * 0.16);
  float macio = 0.03 + 0.16 * alto;
  float dentro = deg(macio, -macio, d);
  float veias = fbm3(Pf * 3.6 + 41.0);
  if (dentro > 0.002) {
    // 1) a cúpula do crânio: alta no meio, despencando perto da beirada
    float rp = clamp(d + 1.0, 0.0, 1.0);
    float tt = max(1.0 - pow(rp, 2.4), 0.0);
    float queda = -0.72 * pow(rp, 1.4) * pow(max(tt, 0.03), -0.4);
    relevo = vec3(0.5 * pow(tt, 0.6), queda * vec2(qe.x / largo, qe.y / altura) / max(rr, 0.001));
    // 2) as massas em par (um lado é o espelho do outro): contas feitas com o rosto "dobrado" ao meio
    vec2 pw = Pf + 0.025 * torce;
    float sx = sqrt(pw.x * pw.x + 0.0009);
    vec2 pf = vec2(sx, pw.y);
    float ang = radians(31.0 + 13.0 * u_inclina);
    vec2 eu = vec2(cos(ang), -sin(ang));          // ao longo do olho: para fora e para cima
    vec2 ev = vec2(-eu.y, eu.x);                  // atravessado: para fora e para baixo
    vec2 co = vec2(0.33, -0.19 + 0.03 * u_inclina);
    vec3 meio = relevo;
    relevo = vec3(0.0);
    massa(pf, co - 0.118 * ev + 0.02 * eu, eu, vec2(0.34, 0.046), 0.100);                      // sobrancelha: uma marquise sobre o olho
    massa(pf, co + 0.02 * ev, eu, vec2(0.34, 0.110), -0.110);                                  // a órbita, cavada fundo
    massa(pf, vec2(0.47, 0.04), vec2(0.94, -0.342), vec2(0.16, 0.052), 0.085);                 // maçã do rosto
    massa(pf, vec2(0.58, 0.01), vec2(0.985, -0.17), vec2(0.10, 0.032), 0.030);                 // o arco da maçã indo para trás
    massa(pf, vec2(0.45, 0.17), vec2(0.94, -0.342), vec2(0.14, 0.055), -0.040);                // a cova embaixo da maçã
    massa(pf, vec2(0.29, 0.12), vec2(0.921, 0.390), vec2(0.16, 0.022), -0.022);                // vinco de rosnado, do meio até o canto da boca
    massa(pf, vec2(0.17, -0.52), vec2(1.0, 0.0), vec2(0.17, 0.15), 0.030);                     // bossa da testa
    massa(pf, vec2(0.45, -0.54), vec2(-0.53, -0.848), vec2(0.20, 0.030), 0.034);               // a quina do crânio: separa a testa da lateral
    massa(pf, vec2(0.53, -0.47), vec2(1.0, 0.0), vec2(0.09, 0.15), -0.040);                    // têmpora
    massa(pf, vec2(0.30, 0.55 + 0.05 * u_boca), vec2(-0.646, 0.763), vec2(0.26, 0.05), 0.045); // borda da mandíbula
    relevo = meio + vec3(relevo.x, relevo.y * pw.x / sx, relevo.z);
    // 3) as massas do meio do rosto
    massa(pw, vec2(0.0, -0.11), vec2(1.0, 0.0), vec2(0.09, 0.08), 0.045);                      // entre as sobrancelhas
    massa(pw, vec2(0.012, -0.50), vec2(0.998, 0.07), vec2(0.08, 0.30), 0.016);                 // crista no meio da testa
    massa(pw, vec2(0.0, 0.23), vec2(1.0, 0.0), vec2(0.34, 0.15), 0.035);                       // focinho
    massa(pw, vec2(0.0, 0.66 + 0.07 * u_boca), vec2(1.0, 0.0), vec2(0.15, 0.09), 0.060);       // queixo
    // 4) os lábios: um rolete logo acima do vão e outro logo abaixo, acompanhando o sorriso
    vec4 lb = linhaDaBoca(pw.x);
    float cantos = deg(0.0, 0.30, lb.z);
    rolete(pw, lb.x - 0.042, lb.w, 0.030, 0.032 * cantos);
    rolete(pw, lb.y + 0.050, lb.w, 0.036, 0.034 * cantos);
    // 5) veios sob a pele, só nas laterais do crânio e da mandíbula (a frente do rosto fica lisa)
    float zona = deg(0.22, 0.42, abs(pw.x)) * (deg(-0.22, -0.38, pw.y) + deg(0.32, 0.46, pw.y)) * (1.0 - deg(0.35, 0.65, alto));
#ifndef LEVE
    if (zona > 0.01) {
      vec2 q = pw * vec2(4.2, 2.6) + vec2(3.1, 7.7);
      float v0 = veio(q), vx = veio(q + vec2(0.0168, 0.0)), vy = veio(q + vec2(0.0, 0.0104));
      float av = 0.006 * zona;
      relevo += vec3(av * v0, av * (vx - v0) / 0.004, av * (vy - v0) / 0.004);
    }
#endif
    vec3 N = virar(normalize(vec3(-relevo.yz + 0.10 * torce, 1.0)));
    vec3 Nl = virar(normalize(vec3(-relevo.yz, 1.0)));             // sem os caroços miúdos: para o reflexo comprido
    float saliencia = relevo.x - meio.x;                    // quanto este ponto está acima (ou abaixo) da cúpula lisa
    float sombra = clamp(1.0 + 8.0 * min(saliencia, 0.0), 0.20, 1.0) * (1.0 + 2.5 * max(saliencia, 0.0));   // covas recebem menos luz, saliências mais
    float some = 1.0 - 0.65 * deg(0.30, 0.80, alto);        // no alto a cabeça vira fumaça: a luz some junto
    float molhado = 0.15 + 0.85 * deg(0.44, 0.60, veias);   // onde a pele está mais lisa e úmida
    vec3 corpo = vec3(0.008, 0.007, 0.022);
    corpo += vec3(0.012, 0.013, 0.034) * (0.4 + 0.6 * clamp(0.5 - 0.7 * N.y, 0.0, 1.0)) * sombra;
    // luz principal: fria, de cima e da esquerda, concentrada na testa
    float foco = exp(-(sq(P.x + 0.18) + sq(P.y + 0.50)) / 0.50);
    float dk = clamp(dot(N, vec3(-0.4002, -0.7805, 0.4803)), 0.0, 1.0);
    float hk = clamp(dot(N, vec3(-0.2326, -0.4535, 0.8605)), 0.0, 1.0);
    corpo += vec3(0.050, 0.056, 0.125) * dk * dk * foco * sombra * some;
    corpo += vec3(0.140, 0.165, 0.370) * pow(hk, 14.0) * foco * sombra * some * (0.6 + 0.4 * molhado);
    // o reflexo molhado: uma tira de luz comprida e fina, que se dobra ao passar pelos relevos
    vec2 dn = Nl.xy - vec2(-0.2326, -0.4535);
    float aoLongo = dot(dn, vec2(0.89, -0.456)), atraves = dot(dn, vec2(0.456, 0.89));
    float tira = 0.50 * exp(-(sq(aoLongo / 0.22) + sq(atraves / 0.085))) + 0.70 * exp(-(sq(aoLongo / 0.16) + sq(atraves / 0.022)));
    corpo += vec3(0.80, 0.86, 1.00) * tira * (0.35 + 0.65 * molhado) * sombra * some * deg(0.06, -0.14, Pf.y);   // só da linha dos olhos para cima
    // pontinhos de brilho onde a pele é mais lisa: o reflexo estreito de vidro escuro, no rosto inteiro
    corpo += vec3(0.75, 0.82, 1.0) * pow(hk, 160.0) * molhado * sombra * (0.35 + 0.65 * foco) * 0.55;
    // vidro escuro: de frente quase não reflete; nas beiradas reflete o ambiente (janela fria em cima, faixa violeta à direita)
    float fres = 0.03 + 0.97 * pow(1.0 - clamp(N.z, 0.0, 1.0), 4.0);
    vec3 R = vec3(2.0 * N.z * N.xy, 2.0 * N.z * N.z - 1.0);
    float janela = deg(0.50, 0.86, dot(R, vec3(-0.45, -0.80, 0.40)));
    float faixa = deg(0.62, 0.90, dot(R, vec3(0.92, -0.10, 0.38)));
    vec3 ambiente = vec3(0.020, 0.018, 0.050) * (0.5 - 0.5 * R.y) + vec3(0.42, 0.48, 0.80) * janela + ROXO * 0.60 * faixa;
    corpo += ambiente * fres * (0.45 + 0.55 * molhado) * (0.4 + 0.6 * sombra) * some;
    // luz de recorte violeta: vem de trás, pela direita
    float kr = deg(0.80, 1.0, dot(N, vec3(0.9068, 0.2699, 0.3239)));
    corpo += ROXO * kr * kr * 0.50 * (0.35 + 0.65 * sombra) * some * (0.55 + 0.45 * molhado);
    // luz violeta de baixo: pega o queixo e a mandíbula
    float kb = deg(0.80, 1.0, dot(N, vec3(-0.160, 0.906, 0.392))) * deg(0.05, 0.55, Pf.y);
    corpo += ROXO * kb * kb * 0.45 * some;
    // a luz dos olhos na pele (some junto quando ele pisca): forte nas paredes da órbita, na marquise e no alto da maçã
    float lo = (luzDoOlho(Pf, N, -1.0, eu, ev) + luzDoOlho(Pf, N, 1.0, eu, ev) * (1.0 - 0.38 * u_torto)) * u_olho
             * (1.0 - 0.85 * clamp(u_palpebra, 0.0, 1.0)) * u_brilho;
    corpo += fogo * lo * 1.30;
    // a boca aberta solta luz violeta nos lábios, no queixo e nas bochechas
    vec3 Lm = vec3(clamp(Pf.x, -0.30, 0.30) - Pf.x, 0.43 + 0.15 * u_boca - Pf.y, 0.09);
    float m2 = dot(Lm, Lm);
    corpo += ROXO * max(dot(N, Lm) * inversesqrt(m2), 0.0) / (1.0 + m2 / 0.03) * 0.65 * deg(0.08, 0.85, u_boca) * some;
    por(corpo, dentro);
  }
  float quebra = (0.35 + 0.65 * deg(0.3, 0.7, veias)) * (1.0 - 0.85 * deg(0.0, 0.55, alto));
  luz(ROXO, exp(-sq(d / 0.030)) * 0.40 * dentro * quebra * borda);
  luz(vec3(0.45, 0.58, 1.0), exp(-sq(d / 0.026)) * 0.15 * dentro * quebra * chave);
  pele = dentro;
}

// um olho: lâmina rasgada, barriguda embaixo, com a beirada de cima em chama.
// Fica dentro de uma órbita: a beirada da órbita é escura, o branco mora no fundo da barriga
// e a parte de cima fica na sombra da sobrancelha; o brilho escapa mais para baixo do que para cima.
void olho(vec2 P, float lado, float abertura, float tam, vec3 cor, vec2 torce) {
  vec2 c = vec2(lado * 0.33, -0.19 + 0.03 * u_inclina);
  float ang = radians(31.0 + 13.0 * u_inclina);
  vec2 r = vec2((P.x - c.x) * lado, P.y - c.y) + 0.02 * torce;
  float u = r.x * cos(ang) - r.y * sin(ang);
  float v = r.x * sin(ang) + r.y * cos(ang);
  float meia = 0.34 * tam;
  float perfil = pow(clamp(1.0 - sq(u / meia), 0.0, 1.0), 0.75);
  float barriga = (0.5 + 0.5 * clamp(u / meia, -1.0, 1.0)) * 0.35 + 0.65;
  float baixo = 0.165 * abertura * tam * perfil * barriga * (1.0 - 0.62 * u_feliz);
  float chama = (fbm3(vec2(u * 7.0, v * 4.0 + u_t * 1.7) + lado * 13.0) - 0.35) * 0.09 * clamp(u / meia + 0.4, 0.0, 1.4);
  float cima = 0.062 * abertura * tam * perfil * (1.0 + 1.1 * u_feliz) + chama * abertura * (1.0 - 0.45 * u_feliz);
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
  luz(cor, exp(-fora / 0.12) * 0.11 * abertura * paraBaixo * (1.0 - palp) * u_brilho);
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

// ---------------------------------------------------------------- a boca
// as medidas de um dente da fileira: onde nasce (x), largura, comprimento e quanto está no meio da boca;
// em pontos fixos nascem presas; de vez em quando um dente sai bem mais comprido
vec4 medidaDente(float k, float n, float meia, float semente, float presaA, float presaB, float escala) {
  float passo = 2.0 * meia / n;
  float centro = (k + 0.5) * passo - meia + (rnd(k + semente + 3.0) - 0.5) * 0.25 * passo;
  float fk = max(0.0, 1.0 - sq(centro / meia));
  float presa = max(max(step(abs(k - presaA), 0.5), step(abs(k - (n - 1.0 - presaA)), 0.5)),
                    max(step(abs(k - presaB), 0.5), step(abs(k - (n - 1.0 - presaB)), 0.5)));
  float longo = step(0.90, rnd(k + semente + 17.0));
  float largura = passo * 0.5 * (0.62 + 0.28 * rnd(k + semente + 7.0) + 0.45 * presa);
  float comprido = ((0.050 + 0.120 * pow(fk, 0.7)) * (0.50 + 0.50 * rnd(k + semente)) + 0.02 * u_boca)
                 * (1.0 + 0.55 * presa + 0.30 * longo) * escala;
  return vec4(centro, largura, comprido, fk);
}
float curvaDente(float k, float semente, float centro) {
  return (rnd(k + semente + 51.0) - 0.5) * 0.014 - (centro < 0.0 ? -1.0 : 1.0) * 0.008;   // foice: as pontas pendem para o meio
}
// onde nasce e para onde aponta um dente: perpendicular à linha da boca (os dentes abrem em leque),
// para dentro do vão; "recuo" empurra a raiz para o fundo (a fileira de trás)
vec4 raizDente(float cx, float sinal, float recuo) {
  vec4 lb = linhaDaBoca(cx);
  float meia = 0.50 + 0.03 * u_feliz;
  float inclVao = (0.035 + 0.30 * u_boca) * 0.6 * pow(max(lb.z, 0.04), -0.4) * (-2.0 * cx / (meia * meia));
  float incl = clamp(sinal > 0.0 ? lb.w : lb.w + inclVao, -1.1, 1.1);
  vec2 dir = normalize(vec2(-incl, 1.0)) * sinal;
  return vec4(vec2(cx, sinal > 0.0 ? lb.x : lb.y) + dir * recuo, dir);
}

// um dente: agulha de base curta e larga e ponta comprida, fina e curva como foice; raiz escura, ponta
// translúcida e molhada, reflexo frio de um lado, contraluz violeta da garganta nas beiradas e a própria sombra
void dente(vec2 p, vec2 raiz, vec2 dir, vec4 md, float curva, float escuro, float contra, float vis) {
  float largura = md.y, comprido = md.z, fk = md.w;
  vec2 lado = vec2(dir.y, -dir.x);
  vec2 qs = p - raiz - vec2(0.007, 0.012);
  float aoS = dot(qs, dir) / comprido;
  float atS = dot(qs, lado) - curva * aoS * aoS;
  float sombraD = deg(0.014, -0.006, abs(atS) - largura * pow(clamp(1.0 - aoS, 0.0, 1.0), 1.7)) * step(-0.05, aoS) * step(aoS, 1.08);
  por(vec3(0.0, 0.0, 0.008), sombraD * 0.55 * vis);
  vec2 q = p - raiz;
  float ao = dot(q, dir) / comprido;                             // 0 na raiz, 1 na ponta
  float at = dot(q, lado) - curva * ao * ao;                     // atravessado, já descontando a curva
  float lar = largura * pow(clamp(1.0 - ao, 0.0, 1.0), 1.7);
  float corpo = deg(0.0028, -0.0028, abs(at) - lar) * step(-0.06, ao) * step(ao, 1.0) * vis;
  if (!(corpo <= 0.0)) {
  float u = clamp(at / max(lar, 0.0008), -1.0, 1.0);
  float redondo = sqrt(max(1.0 - u * u, 0.0));
  float pontaV = clamp(ao, 0.0, 1.0);
  vec3 esmalte = vec3(0.97, 0.95, 0.96) * (0.66 + 0.34 * redondo);
  esmalte *= 0.45 + 0.55 * deg(0.0, 0.30, ao);                   // a raiz afunda no escuro da gengiva
  vec3 translucido = mix(vec3(0.55, 0.42, 0.90), vec3(0.78, 0.45, 1.0), u_boca);
  esmalte = mix(esmalte, translucido * (0.6 + 0.4 * redondo), pontaV * pontaV * (0.30 + 0.25 * u_boca));
  esmalte += vec3(0.75, 0.85, 1.0) * exp(-sq((u + 0.35) / 0.16)) * (0.30 + 0.70 * clamp(ao * 1.5, 0.0, 1.0)) * 0.38;
  esmalte += vec3(0.85, 0.90, 1.0) * exp(-sq((ao - 0.90) / 0.06)) * exp(-sq((u + 0.2) / 0.5)) * 0.30;   // ponta molhada
  esmalte += vec3(0.60, 0.25, 0.95) * pow(abs(u), 5.0) * contra;                                       // contraluz violeta
  por(min(esmalte, vec3(1.0)) * escuro * (0.60 + 0.40 * fk), corpo);
  }
}

// uma fileira de dentes: acha a faixa do dente que passaria por este ponto (já contando a inclinação do leque)
// e olha esse e os dois vizinhos; os maiores são desenhados por último, com a sombra caindo nos menores
void fileira(vec2 p, float n, float sinal, float semente, float escuro, float presaA, float presaB,
             float recuo, float escala, float contra, float vis) {
  float meia = 0.50 + 0.03 * u_feliz;
  vec4 lb = linhaDaBoca(p.x);
  float xr = p.x + lb.w * (p.y - (sinal > 0.0 ? lb.x : lb.y));
  float k = floor((xr + meia) / (2.0 * meia) * n);
  float ka = k - 1.0, kb = k, kc = k + 1.0;
  vec4 ma = medidaDente(ka, n, meia, semente, presaA, presaB, escala);
  vec4 mb = medidaDente(kb, n, meia, semente, presaA, presaB, escala);
  vec4 mc = medidaDente(kc, n, meia, semente, presaA, presaB, escala);
  vec4 tv; float tk;
  if (ma.z > mb.z) { tv = ma; ma = mb; mb = tv; tk = ka; ka = kb; kb = tk; }
  if (mb.z > mc.z) { tv = mb; mb = mc; mc = tv; tk = kb; kb = kc; kc = tk; }
  if (ma.z > mb.z) { tv = ma; ma = mb; mb = tv; tk = ka; ka = kb; kb = tk; }
  vec4 rd;
#ifndef LEVE
  if (ka >= 0.0 && ka < n) { rd = raizDente(ma.x, sinal, recuo); dente(p, rd.xy, rd.zw, ma, curvaDente(ka, semente, ma.x), escuro, contra, vis); }
#endif
  if (kb >= 0.0 && kb < n) { rd = raizDente(mb.x, sinal, recuo); dente(p, rd.xy, rd.zw, mb, curvaDente(kb, semente, mb.x), escuro, contra, vis); }
#ifndef LEVE
  if (kc >= 0.0 && kc < n) { rd = raizDente(mc.x, sinal, recuo); dente(p, rd.xy, rd.zw, mc, curvaDente(kc, semente, mc.x), escuro, contra, vis); }
#endif
}

// a língua: um tubo comprido que afina, vem do fundo da boca e, quando "ext" sobe, sai por cima dos dentes
// de baixo e pende sobre o queixo, balançando. Molhada, com um sulco no meio.
void lingua(vec2 p, float cima, float baixo, float ext, float interior) {
  float vao = baixo - cima;
  float balanca = 0.05 * sin(u_t * 2.3) + 0.03 * sin(u_t * 5.1);
  vec2 base = vec2(0.0, cima + vao * 0.60);
  vec2 ctrl = vec2(balanca * 0.6 + 0.04 * sin(u_t * 1.7), baixo + 0.02 + ext * 0.10);
  vec2 ponta = vec2(balanca * (0.5 + 1.2 * ext) + 0.06 * ext * sin(u_t * 1.3), baixo - 0.02 + ext * 0.38);
  float melhor = 9.0, tMelhor = 0.0, ladoS = 1.0;
  vec2 a = base;
  for (int i = 1; i <= 8; i++) {
    float t = float(i) / 8.0;
    vec2 b = mix(mix(base, ctrl, t), mix(ctrl, ponta, t), t);
    vec2 ab = b - a;
    float h = clamp(dot(p - a, ab) / dot(ab, ab), 0.0, 1.0);
    vec2 w = p - a - ab * h;
    float dd = length(w);
    if (dd < melhor) { melhor = dd; tMelhor = (float(i) - 1.0 + h) / 8.0; ladoS = ab.x * w.y - ab.y * w.x < 0.0 ? -1.0 : 1.0; }
    a = b;
  }
  float largura = 0.095 * (1.0 - pow(tMelhor, 2.2)) * (0.75 + 0.25 * u_boca);   // larga e chata, afinando até a ponta
  float fora = step(baixo - 0.006, p.y) * step(0.30, ext);       // a parte que já saiu da boca
  float corpo = deg(0.004, -0.004, melhor - largura) * max(interior, fora) * deg(0.0, 0.25, ext + u_boca);
  if (!(corpo <= 0.0)) {
  float us = ladoS * melhor / max(largura, 0.001);               // -1 a 1, de um lado ao outro
  float tubo = pow(max(1.0 - us * us, 0.0), 0.25);
  vec3 c = vec3(0.36, 0.07, 0.38) * (0.45 + 0.55 * tubo);
  c *= 1.0 - 0.40 * exp(-sq(us / 0.12));                         // o sulco no meio
  c += vec3(0.85, 0.75, 1.0) * exp(-sq((us + 0.45) / 0.14)) * 0.42;   // molhada
  c += vec3(0.55, 0.20, 0.80) * (1.0 - tMelhor) * u_boca * 0.25;      // perto do fundo, a luz da garganta
  por(c, corpo);
  }
}

// um fio de saliva entre as mandíbulas: grosso no meio, fino onde gruda, com uma gota escorrendo
float fioSaliva(vec2 p, float xs, float cima, float vao, float fase) {
  float fundo = clamp((p.y - cima) / max(vao, 0.001), 0.0, 1.0);
  float arco = sin(3.14159 * fundo);
  float x = xs + 0.010 * sin(p.y * 30.0 + u_t * 2.5 + fase) + 0.016 * arco * sin(fase * 2.3);
  float w = (0.0030 + 0.0060 * pow(arco, 0.6)) * (1.30 - 0.60 * u_boca);
  float yg = cima + vao * (0.15 + 0.70 * fract(u_t * 0.22 + fase * 0.17));
  w += 0.0065 * exp(-sq((p.y - yg) / 0.012));
  return exp(-sq((p.x - x) / w));
}

// a boca: um rasgo de bochecha a bochecha, com lábio vincado e úmido. Aberta, é uma cavidade funda: céu da
// boca com dobras, paredes escurecendo nos cantos, a garganta acesa lá no fundo, duas fileiras de dentes
// (a de trás menor e no escuro), saliva grossa e a língua, que às vezes sai.
void boca(vec2 P, vec2 torce) {
  float x = P.x + 0.012 * torce.x, y = P.y + 0.012 * torce.y;
  vec2 p = vec2(x, y);
  vec4 lb = linhaDaBoca(x);
  float meia = 0.50 + 0.03 * u_feliz;
  float canto = 0.20 - 0.05 * u_feliz + 0.05 * u_torto;
  float cima = lb.x, baixo = lb.y, vao = baixo - cima;
  float dentroX = step(abs(x), meia);
  float d = dentroX > 0.5 ? abs(y - (cima + baixo) * 0.5) - vao * 0.5 : length(vec2(abs(x) - meia, y - canto));
  if (!(d > 0.45)) {
  float aberta = deg(0.05, 0.60, u_boca);
  float ext = clamp(u_lingua, 0.0, 1.0);
  // a luz violeta que vaza pelo vão
  luz(ROXO, exp(-max(d, 0.0) / 0.040) * (0.04 + 0.11 * aberta));
  // o vinco do lábio: escuro, colado ao vão; logo fora, um fio de reflexo molhado no lábio de cima
  por(vec3(0.0, 0.0, 0.006), deg(0.032, 0.002, d) * 0.80);
  float acima = step(y, (cima + baixo) * 0.5);
  float ladoB = x < 0.0 ? -1.0 : 1.0;
  vec2 dirV = vec2(ladoB * 0.55, -0.835);
  vec2 qv = vec2(x - ladoB * meia, y - canto);
  float alV = clamp(dot(qv, dirV), 0.0, 0.075);
  float dV = length(qv - dirV * alV);
  float vaiV = (1.0 - alV / 0.075) * step(-0.01, dot(qv, dirV));
  por(vec3(0.0, 0.0, 0.006), exp(-sq(dV / 0.007)) * vaiV * 0.80);
  luz(vec3(0.55, 0.62, 0.95), exp(-sq((dV - 0.012) / 0.004)) * vaiV * 0.16 * step(qv.y, dirV.y * alV));
  luz(vec3(0.62, 0.72, 1.0), exp(-sq((d - 0.024) / 0.0065)) * 0.20 * acima * deg(0.0, 0.35, lb.z) * (0.4 + 0.6 * deg(0.35, 0.65, fbm3(vec2(x * 9.0, 3.0)))));
  float interior = deg(0.008, -0.008, d);
  float fundo = clamp((y - cima) / max(vao, 0.001), 0.0, 1.0);
  // a cavidade: preta perto das beiradas e dos cantos; dobras em arco no céu da boca; a garganta acesa no fundo
  float garganta = exp(-(sq(x / (0.18 + 0.10 * aberta)) + sq((fundo - 0.60) / 0.30))) * u_boca;
  vec3 cav = vec3(0.008, 0.004, 0.018) + vec3(0.40, 0.12, 0.60) * garganta * 0.90;
  cav *= 0.45 + 0.55 * deg(0.0, 0.30, min(fundo, 1.0 - fundo) * 2.0);
  float rugas = 0.5 + 0.5 * sin((fundo * 9.0 + x * x * 14.0) * 3.14159);
  cav *= 1.0 - 0.35 * rugas * (1.0 - deg(0.10, 0.45, fundo)) * aberta;
  cav *= 0.55 + 0.45 * deg(meia * 0.98, meia * 0.45, abs(x));
  por(cav, interior);
  // as gengivas: uma faixa escura e úmida rente aos dentes, com um fio de luz na beirada
  float gengiva = exp(-sq((y - cima) / 0.016)) + exp(-sq((y - baixo) / 0.016));
  por(vec3(0.09, 0.018, 0.10), interior * gengiva * 0.80 * aberta);
  luz(vec3(0.55, 0.30, 0.75), interior * (exp(-sq((y - cima - 0.013) / 0.0045)) + exp(-sq((y - baixo + 0.013) / 0.0045))) * 0.30 * aberta);
#ifndef LEVE
  // a fileira de trás: menor, no escuro, só aparece com a boca aberta
  float atras = interior * aberta;
  if (atras > 0.0) {
    fileira(p, 15.0, -1.0, 37.0, 0.26, -9.0, -9.0, 0.040, 0.55, 0.55 * aberta, atras);
    fileira(p, 16.0, 1.0, 113.0, 0.30, -9.0, -9.0, 0.040, 0.60, 0.55 * aberta, atras);
  }
  // saliva grossa entre as presas
  float temFio = interior * deg(0.38, 0.6, u_boca);
  if (temFio > 0.0) {
    float fio = max(max(fioSaliva(p, -0.33, cima, vao, 0.0), fioSaliva(p, -0.16, cima, vao, 1.7)),
                    max(fioSaliva(p, 0.19, cima, vao, 3.1), fioSaliva(p, 0.35, cima, vao, 4.4)));
    por(vec3(0.50, 0.40, 0.78), fio * temFio * 0.70);
    luz(vec3(0.80, 0.85, 1.0), fio * temFio * 0.20);
  }
  if (ext < 0.35) lingua(p, cima, baixo, ext, interior);         // dentro: atrás dos dentes de baixo
#endif
  fileira(p, 19.0, -1.0, 5.0, 0.86, 4.0, -9.0, 0.0, 1.0, 0.45 * aberta, 1.0);
  // a sombra do lábio de cima caindo para dentro da boca (escurece as pontas dos dentes de baixo)
  por(vec3(0.0, 0.0, 0.010), interior * exp(-sq((y - cima) / 0.035)) * 0.50 * aberta);
#ifndef LEVE
  if (ext >= 0.35) lingua(p, cima, baixo, ext, interior);
#endif        // saindo: na frente dos dentes de baixo
  fileira(p, 20.0, 1.0, 71.0, 1.0, 3.0, 8.0, 0.0, 1.0, 0.45 * aberta, 1.0);
  }
}

void main() {
#ifdef NO_APP
  vec2 uv = vec2(tex_coord0.x, 1.0 - tex_coord0.y);   // (no Kivy a textura vem de cabeça para baixo)
#else
  vec2 uv = gl_FragCoord.xy / u_res;
#endif
  vec2 P = vec2(uv.x * 2.0 - 1.0, 1.0 - uv.y * 2.0);            // y cresce para baixo
  P.y -= 0.015 * sin(u_t * 1.3);                                 // a cabeça respira
  // a cabeça de lado: gira no plano da tela, em volta do pescoço
  float cr = cos(u_rolar), sr = sin(u_rolar);
  P = vec2(cr * P.x + sr * (P.y - 0.25), -sr * P.x + cr * (P.y - 0.25) + 0.25);
  // virando e acenando: o meio do rosto, que está mais à frente, anda mais que a beirada
  vec2 qd = vec2(P.x / 0.66, (P.y + 0.06) / 0.80);
  vec2 Pf = P - u_giro * 0.16 * sqrt(max(1.0 - dot(qd, qd), 0.0));
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
  boca(Pf, torce);
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
  // aparecendo/sumindo: o rosto se forma da fumaça escura, de dentro para fora, com a borda
  // acesa em roxo (u_presenca de 0 a 1); sumindo, desfaz do mesmo jeito
  float pr = clamp(u_presenca, 0.0, 1.0);
  if (pr < 0.999) {
    float nz = fbm3(P * 2.8 + vec2(0.0, u_t * 0.7));
    float campo = nz * 0.75 + length(P) * 0.35;           // o meio forma primeiro
    float lim = mix(-0.05, 1.30, pr);
    float dentro = smoothstep(lim, lim - 0.12, campo);    // 1 = já formado
    float borda = exp(-sq((campo - lim) / 0.045)) * min(alfa * 2.0, 1.0);
    float fum = smoothstep(lim + 0.40, lim, campo) * (1.0 - dentro) * 4.0 * pr * (1.0 - pr) * 0.75
                * smoothstep(0.95, 0.55, length(P * vec2(1.0, 0.9)));   // só em volta dele, nunca o quadrado
    col *= dentro;
    alfa *= dentro;
    fum *= semBeira;
    col += ROXO * borda * 0.9 + vec3(0.015, 0.008, 0.035) * fum;
    alfa += borda * 0.7 + fum;
    alfa = min(alfa, 1.0);
  }
  // o Kivy mistura com a cor "pura": desfaz a multiplicação pela transparência
  gl_FragColor = vec4(min(col / max(alfa, 0.004), vec3(1.0)), alfa * min(pr * 3.0, 1.0));
#else
  gl_FragColor = vec4(col, alfa);
#endif
}
'''
