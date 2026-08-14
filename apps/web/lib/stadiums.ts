export type Stadium = {
  stadium: string;
  city: string;
  coordinates: [number, number]; // [lng, lat]
  code: string;
};

export type LeagueMapConfig = {
  countries: string[];
  center: [number, number];
  scale: number;
  statesGeo: string;
  teams: Record<string, Stadium>;
};

export const LEAGUE_MAPS: Record<string, LeagueMapConfig> = {
  mls: {
    countries: ["United States of America", "Canada"],
    statesGeo: "https://cdn.jsdelivr.net/npm/us-atlas@3/states-10m.json",
    center: [-96, 42],
    scale: 430,
    teams: {
      "Atlanta United": { stadium: "Mercedes-Benz Stadium", city: "Atlanta", coordinates: [-84.4008, 33.7554], code: "ATL" },
      "Austin FC": { stadium: "Q2 Stadium", city: "Austin", coordinates: [-97.7305, 30.3877], code: "ATX" },
      "Charlotte FC": { stadium: "Bank of America Stadium", city: "Charlotte", coordinates: [-80.8529, 35.2258], code: "CLT" },
      "Chicago Fire FC": { stadium: "Soldier Field", city: "Chicago", coordinates: [-87.6167, 41.8623], code: "CHI" },
      "FC Cincinnati": { stadium: "TQL Stadium", city: "Cincinnati", coordinates: [-84.5161, 39.1114], code: "CIN" },
      "Colorado Rapids": { stadium: "Dick's Sporting Goods Park", city: "Commerce City", coordinates: [-104.8918, 39.8057], code: "COL" },
      "Columbus Crew": { stadium: "Lower.com Field", city: "Columbus", coordinates: [-83.0171, 39.9685], code: "CLB" },
      "DC United": { stadium: "Audi Field", city: "Washington", coordinates: [-77.0128, 38.868], code: "DCU" },
      "FC Dallas": { stadium: "Toyota Stadium", city: "Frisco", coordinates: [-96.8353, 33.1543], code: "DAL" },
      "Houston Dynamo FC": { stadium: "Shell Energy Stadium", city: "Houston", coordinates: [-95.3522, 29.7522], code: "HOU" },
      "Inter Miami CF": { stadium: "Miami Freedom Park", city: "Miami", coordinates: [-80.2061, 25.7811], code: "MIA" },
      "LA Galaxy": { stadium: "Dignity Health Sports Park", city: "Carson", coordinates: [-118.2611, 33.8644], code: "LAG" },
      "Los Angeles FC": { stadium: "BMO Stadium", city: "Los Angeles", coordinates: [-118.2849, 34.0128], code: "LAFC" },
      "Minnesota United": { stadium: "Allianz Field", city: "St. Paul", coordinates: [-93.1654, 44.9532], code: "MIN" },
      "CF Montreal": { stadium: "Stade Saputo", city: "Montreal", coordinates: [-73.5525, 45.5631], code: "MTL" },
      "Nashville SC": { stadium: "GEODIS Park", city: "Nashville", coordinates: [-86.7677, 36.1302], code: "NSH" },
      "New England Revolution": { stadium: "Gillette Stadium", city: "Foxborough", coordinates: [-71.2643, 42.0909], code: "NE" },
      "New York City FC": { stadium: "Yankee Stadium", city: "New York", coordinates: [-73.9262, 40.8296], code: "NYC" },
      "Red Bull New York": { stadium: "Sports Illustrated Stadium", city: "Harrison", coordinates: [-74.1502, 40.7368], code: "RBNY" },
      "Orlando City": { stadium: "Inter&Co Stadium", city: "Orlando", coordinates: [-81.3892, 28.5411], code: "ORL" },
      "Philadelphia Union": { stadium: "Subaru Park", city: "Chester", coordinates: [-75.3785, 39.8329], code: "PHI" },
      "Portland Timbers": { stadium: "Providence Park", city: "Portland", coordinates: [-122.6918, 45.5215], code: "POR" },
      "Real Salt Lake": { stadium: "America First Field", city: "Sandy", coordinates: [-111.8932, 40.5829], code: "RSL" },
      "San Diego FC": { stadium: "Snapdragon Stadium", city: "San Diego", coordinates: [-117.1225, 32.784], code: "SD" },
      "San Jose Earthquakes": { stadium: "PayPal Park", city: "San Jose", coordinates: [-121.9252, 37.3512], code: "SJ" },
      "Seattle Sounders FC": { stadium: "Lumen Field", city: "Seattle", coordinates: [-122.3316, 47.5952], code: "SEA" },
      "Sporting Kansas City": { stadium: "Children's Mercy Park", city: "Kansas City", coordinates: [-94.8233, 39.1216], code: "SKC" },
      "St. Louis City": { stadium: "Energizer Park", city: "St. Louis", coordinates: [-90.2102, 38.6312], code: "STL" },
      "Toronto FC": { stadium: "BMO Field", city: "Toronto", coordinates: [-79.4186, 43.6332], code: "TOR" },
      "Vancouver Whitecaps": { stadium: "BC Place", city: "Vancouver", coordinates: [-123.1119, 49.2768], code: "VAN" },
    },
  },
  "premier-league": {
    countries: ["United Kingdom"],
    statesGeo: "/geo/united-kingdom-states.json",
    center: [-1.6, 52.8],
    scale: 3400,
    teams: {
      Arsenal: { stadium: "Emirates Stadium", city: "London", coordinates: [-0.1086, 51.5549], code: "ARS" },
      "Aston Villa": { stadium: "Villa Park", city: "Birmingham", coordinates: [-1.885, 52.5092], code: "AVL" },
      Bournemouth: { stadium: "Vitality Stadium", city: "Bournemouth", coordinates: [-1.8384, 50.7352], code: "BOU" },
      Brentford: { stadium: "Gtech Community Stadium", city: "London", coordinates: [-0.2886, 51.4907], code: "BRE" },
      Brighton: { stadium: "Amex Stadium", city: "Brighton", coordinates: [-0.0837, 50.8616], code: "BHA" },
      Burnley: { stadium: "Turf Moor", city: "Burnley", coordinates: [-2.2302, 53.789], code: "BUR" },
      Chelsea: { stadium: "Stamford Bridge", city: "London", coordinates: [-0.191, 51.4817], code: "CHE" },
      "Crystal Palace": { stadium: "Selhurst Park", city: "London", coordinates: [-0.0857, 51.3983], code: "CRY" },
      Everton: { stadium: "Hill Dickinson Stadium", city: "Liverpool", coordinates: [-3.0008, 53.4319], code: "EVE" },
      Fulham: { stadium: "Craven Cottage", city: "London", coordinates: [-0.2216, 51.4749], code: "FUL" },
      Leeds: { stadium: "Elland Road", city: "Leeds", coordinates: [-1.5722, 53.7778], code: "LEE" },
      Liverpool: { stadium: "Anfield", city: "Liverpool", coordinates: [-2.9608, 53.4308], code: "LIV" },
      "Man City": { stadium: "Etihad Stadium", city: "Manchester", coordinates: [-2.2004, 53.4831], code: "MCI" },
      "Man Utd": { stadium: "Old Trafford", city: "Manchester", coordinates: [-2.2913, 53.4631], code: "MUN" },
      Newcastle: { stadium: "St James' Park", city: "Newcastle", coordinates: [-1.6217, 54.9756], code: "NEW" },
      "Nottingham Forest": { stadium: "The City Ground", city: "Nottingham", coordinates: [-1.1329, 52.9399], code: "NFO" },
      Sunderland: { stadium: "Stadium of Light", city: "Sunderland", coordinates: [-1.3883, 54.9146], code: "SUN" },
      Tottenham: { stadium: "Tottenham Hotspur Stadium", city: "London", coordinates: [-0.0665, 51.6043], code: "TOT" },
      "West Ham": { stadium: "London Stadium", city: "London", coordinates: [-0.0166, 51.5387], code: "WHU" },
      Wolves: { stadium: "Molineux", city: "Wolverhampton", coordinates: [-2.1304, 52.5903], code: "WOL" },
    },
  },
  laliga: {
    countries: ["Spain"],
    statesGeo: "/geo/spain-states.json",
    center: [-3.0, 40.0],
    scale: 2400,
    teams: {
      "Atletic Club": { stadium: "San Mamés", city: "Bilbao", coordinates: [-2.9494, 43.2641], code: "ATH" },
      "Atletico Madrid": { stadium: "Metropolitano", city: "Madrid", coordinates: [-3.5995, 40.4362], code: "ATM" },
      Barcelona: { stadium: "Camp Nou", city: "Barcelona", coordinates: [2.1228, 41.3809], code: "BAR" },
      "Celta Vigo": { stadium: "Balaídos", city: "Vigo", coordinates: [-8.7397, 42.2118], code: "CEL" },
      "Deportivo Alaves": { stadium: "Mendizorroza", city: "Vitoria-Gasteiz", coordinates: [-2.6884, 42.8371], code: "ALA" },
      Elche: { stadium: "Martínez Valero", city: "Elche", coordinates: [-0.6605, 38.2669], code: "ELC" },
      Espanyol: { stadium: "RCDE Stadium", city: "Barcelona", coordinates: [2.0755, 41.3479], code: "ESP" },
      Getafe: { stadium: "Coliseum", city: "Getafe", coordinates: [-3.7146, 40.3256], code: "GET" },
      Girona: { stadium: "Montilivi", city: "Girona", coordinates: [2.8286, 41.9613], code: "GIR" },
      Levante: { stadium: "Ciutat de València", city: "Valencia", coordinates: [-0.3645, 39.4948], code: "LEV" },
      Mallorca: { stadium: "Son Moix", city: "Palma", coordinates: [2.63, 39.59], code: "MLL" },
      Osasuna: { stadium: "El Sadar", city: "Pamplona", coordinates: [-1.6369, 42.7968], code: "OSA" },
      "Rayo Vallecano": { stadium: "Vallecas", city: "Madrid", coordinates: [-3.6588, 40.3919], code: "RAY" },
      "Real Betis": { stadium: "Benito Villamarín", city: "Seville", coordinates: [-5.9816, 37.3564], code: "BET" },
      "Real Madrid": { stadium: "Santiago Bernabéu", city: "Madrid", coordinates: [-3.6883, 40.4531], code: "RMA" },
      "Real Oviedo": { stadium: "Carlos Tartiere", city: "Oviedo", coordinates: [-5.8737, 43.3603], code: "OVI" },
      "Real Sociedad": { stadium: "Anoeta", city: "San Sebastián", coordinates: [-1.9736, 43.3014], code: "RSO" },
      Sevilla: { stadium: "Sánchez-Pizjuán", city: "Seville", coordinates: [-5.9705, 37.3841], code: "SEV" },
      Valencia: { stadium: "Mestalla", city: "Valencia", coordinates: [-0.3585, 39.4747], code: "VAL" },
      Villarreal: { stadium: "La Cerámica", city: "Villarreal", coordinates: [-0.1037, 39.9441], code: "VIL" },
    },
  },
  bundesliga: {
    countries: ["Germany"],
    statesGeo: "/geo/germany-states.json",
    center: [10.3, 51.2],
    scale: 2700,
    teams: {
      Augsburg: { stadium: "WWK Arena", city: "Augsburg", coordinates: [10.8859, 48.3231], code: "FCA" },
      "Bayer Leverkusen": { stadium: "BayArena", city: "Leverkusen", coordinates: [7.0022, 51.0382], code: "B04" },
      "Bayern Munich": { stadium: "Allianz Arena", city: "Munich", coordinates: [11.6247, 48.2188], code: "FCB" },
      "Borussia Dortmund": { stadium: "Signal Iduna Park", city: "Dortmund", coordinates: [7.4517, 51.4926], code: "BVB" },
      "Borussia M.Gladbach": { stadium: "Borussia-Park", city: "Mönchengladbach", coordinates: [6.3855, 51.1746], code: "BMG" },
      "Eintracht Frankfurt": { stadium: "Deutsche Bank Park", city: "Frankfurt", coordinates: [8.6455, 50.0686], code: "SGE" },
      "FC Heidenheim": { stadium: "Voith-Arena", city: "Heidenheim", coordinates: [10.1394, 48.6684], code: "FCH" },
      "FC Koln": { stadium: "RheinEnergieStadion", city: "Cologne", coordinates: [6.8752, 50.9335], code: "KOE" },
      Freiburg: { stadium: "Europa-Park Stadion", city: "Freiburg", coordinates: [7.8931, 48.0216], code: "SCF" },
      "Hamburger SV": { stadium: "Volksparkstadion", city: "Hamburg", coordinates: [9.8987, 53.5872], code: "HSV" },
      Hoffenheim: { stadium: "PreZero Arena", city: "Sinsheim", coordinates: [8.888, 49.238], code: "TSG" },
      "Mainz 05": { stadium: "Mewa Arena", city: "Mainz", coordinates: [8.2243, 49.984], code: "M05" },
      "RB Leipzig": { stadium: "Red Bull Arena", city: "Leipzig", coordinates: [12.348, 51.3458], code: "RBL" },
      "St. Pauli": { stadium: "Millerntor-Stadion", city: "Hamburg", coordinates: [9.9677, 53.5546], code: "STP" },
      "Union Berlin": { stadium: "Alte Försterei", city: "Berlin", coordinates: [13.5681, 52.4574], code: "FCU" },
      "VfB Stuttgart": { stadium: "MHPArena", city: "Stuttgart", coordinates: [9.2321, 48.7922], code: "VFB" },
      "Werder Bremen": { stadium: "Weserstadion", city: "Bremen", coordinates: [8.8375, 53.0664], code: "SVW" },
      Wolfsburg: { stadium: "Volkswagen Arena", city: "Wolfsburg", coordinates: [10.8038, 52.4327], code: "WOB" },
    },
  },
  "serie-a": {
    countries: ["Italy"],
    statesGeo: "/geo/italy-states.json",
    center: [12.5, 42.4],
    scale: 2400,
    teams: {
      "AC Milan": { stadium: "San Siro", city: "Milan", coordinates: [9.124, 45.4781], code: "MIL" },
      Atalanta: { stadium: "Gewiss Stadium", city: "Bergamo", coordinates: [9.6807, 45.7089], code: "ATA" },
      Bologna: { stadium: "Renato Dall'Ara", city: "Bologna", coordinates: [11.3097, 44.4939], code: "BOL" },
      Cagliari: { stadium: "Unipol Domus", city: "Cagliari", coordinates: [9.135, 39.1999], code: "CAG" },
      Como: { stadium: "Giuseppe Sinigaglia", city: "Como", coordinates: [9.0752, 45.813], code: "COM" },
      Cremonese: { stadium: "Giovanni Zini", city: "Cremona", coordinates: [10.0413, 45.1406], code: "CRE" },
      Fiorentina: { stadium: "Artemio Franchi", city: "Florence", coordinates: [11.2823, 43.7809], code: "FIO" },
      Genoa: { stadium: "Luigi Ferraris", city: "Genoa", coordinates: [8.9525, 44.4164], code: "GEN" },
      Inter: { stadium: "San Siro", city: "Milan", coordinates: [9.155, 45.462], code: "INT" },
      Juventus: { stadium: "Allianz Stadium", city: "Turin", coordinates: [7.6413, 45.1096], code: "JUV" },
      Lazio: { stadium: "Stadio Olimpico", city: "Rome", coordinates: [12.4547, 41.9339], code: "LAZ" },
      Lecce: { stadium: "Via del Mare", city: "Lecce", coordinates: [18.209, 40.3654], code: "LEC" },
      Napoli: { stadium: "Diego Armando Maradona", city: "Naples", coordinates: [14.193, 40.828], code: "NAP" },
      "Parma Calcio": { stadium: "Ennio Tardini", city: "Parma", coordinates: [10.3387, 44.795], code: "PAR" },
      Pisa: { stadium: "Arena Garibaldi", city: "Pisa", coordinates: [10.4004, 43.7273], code: "PIS" },
      Roma: { stadium: "Stadio Olimpico", city: "Rome", coordinates: [12.478, 41.925], code: "ROM" },
      Sassuolo: { stadium: "Mapei Stadium", city: "Reggio Emilia", coordinates: [10.6486, 44.7145], code: "SAS" },
      Torino: { stadium: "Olimpico Grande Torino", city: "Turin", coordinates: [7.65, 45.0419], code: "TOR" },
      Udinese: { stadium: "Bluenergy Stadium", city: "Udine", coordinates: [13.2001, 46.0816], code: "UDI" },
      Verona: { stadium: "Marcantonio Bentegodi", city: "Verona", coordinates: [10.9686, 45.4353], code: "VER" },
    },
  },
  "ligue-1": {
    countries: ["France", "Monaco"],
    statesGeo: "/geo/france-states.json",
    center: [2.6, 46.8],
    scale: 2400,
    teams: {
      Angers: { stadium: "Raymond Kopa", city: "Angers", coordinates: [-0.5307, 47.4604], code: "ANG" },
      Auxerre: { stadium: "Abbé-Deschamps", city: "Auxerre", coordinates: [3.5886, 47.7867], code: "AJA" },
      Brest: { stadium: "Francis-Le Blé", city: "Brest", coordinates: [-4.4617, 48.4029], code: "BRE" },
      "Le Havre": { stadium: "Stade Océane", city: "Le Havre", coordinates: [0.1699, 49.4989], code: "HAC" },
      Lens: { stadium: "Bollaert-Delelis", city: "Lens", coordinates: [2.815, 50.4328], code: "RCL" },
      Lille: { stadium: "Pierre-Mauroy", city: "Lille", coordinates: [3.1305, 50.612], code: "LIL" },
      Lorient: { stadium: "Le Moustoir", city: "Lorient", coordinates: [-3.369, 47.7486], code: "FCL" },
      Lyon: { stadium: "Groupama Stadium", city: "Lyon", coordinates: [4.982, 45.7653], code: "OL" },
      Marseille: { stadium: "Vélodrome", city: "Marseille", coordinates: [5.3958, 43.2696], code: "OM" },
      Metz: { stadium: "Saint-Symphorien", city: "Metz", coordinates: [6.1595, 49.1098], code: "MET" },
      Monaco: { stadium: "Louis II", city: "Monaco", coordinates: [7.4154, 43.7276], code: "ASM" },
      Nantes: { stadium: "La Beaujoire", city: "Nantes", coordinates: [-1.5253, 47.256], code: "NAN" },
      Nice: { stadium: "Allianz Riviera", city: "Nice", coordinates: [7.1926, 43.7053], code: "NIC" },
      PSG: { stadium: "Parc des Princes", city: "Paris", coordinates: [2.253, 48.8414], code: "PSG" },
      "Paris FC": { stadium: "Stade Charléty", city: "Paris", coordinates: [2.3467, 48.8186], code: "PFC" },
      Rennes: { stadium: "Roazhon Park", city: "Rennes", coordinates: [-1.7129, 48.1075], code: "REN" },
      Strasbourg: { stadium: "La Meinau", city: "Strasbourg", coordinates: [7.755, 48.56], code: "RCS" },
      Toulouse: { stadium: "Stadium de Toulouse", city: "Toulouse", coordinates: [1.434, 43.5833], code: "TFC" },
    },
  },
};

import { CLUB_LOGOS } from "./clubLogos";

const normalize = (name: string) => name.toLowerCase().replace(/[^a-z0-9]/g, "");

export function findStadium(league: string, teamName: string): Stadium | null {
  const config = LEAGUE_MAPS[league];
  if (!config) return null;
  const direct = config.teams[teamName];
  if (direct) return direct;
  const wanted = normalize(teamName);
  for (const [key, stadium] of Object.entries(config.teams)) {
    const known = normalize(key);
    if (known === wanted || known.includes(wanted) || wanted.includes(known)) return stadium;
  }
  return null;
}

export function teamCode(league: string, teamName: string): string {
  const stadium = findStadium(league, teamName);
  if (stadium) return stadium.code;
  const words = teamName.split(/\s+/).filter(Boolean);
  if (words.length >= 2) return (words[0][0] + words[1][0] + (words[1][1] ?? "")).toUpperCase();
  return teamName.slice(0, 3).toUpperCase();
}

export function teamLogo(teamName: string): string | null {
  return CLUB_LOGOS[teamName] ?? null;
}
