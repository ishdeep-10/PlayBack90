export type GlossaryTerm = { term: string; definition: string };

export const GLOSSARY: Record<string, GlossaryTerm[]> = {
  "match-dynamics": [
    { term: "xG (Expected Goals)", definition: "The probability that a shot results in a goal, based on shot location, angle, and situation. Summing xG shows the quality of chances a team created." },
    { term: "xG Flow", definition: "Cumulative xG per team across the match. Steep climbs show periods of sustained pressure; a step marks a high-quality chance." },
    { term: "xT (Expected Threat)", definition: "Credit for moving the ball into more dangerous areas. Unlike xG, it rewards buildup actions (passes and carries) that don't end in a shot." },
    { term: "xT Momentum", definition: "Rolling balance of expected threat between the teams — bars above the axis mean the home side is generating more danger in that window." },
    { term: "PPDA", definition: "Passes allowed Per Defensive Action — opposition passes divided by your pressing actions in their buildup areas. Lower = more aggressive press." },
    { term: "Turnovers", definition: "Times a team lost possession. Frequent turnovers in your own half usually signal trouble under pressure." },
    { term: "Big Chances", definition: "Situations where the shooter is reasonably expected to score, e.g. one-on-ones or close-range attempts (created, with missed shown in brackets)." },
  ],
  shots: [
    { term: "xG (Expected Goals)", definition: "The probability that a shot becomes a goal given its location and context. A 0.35 xG shot scores roughly 1 in 3 times." },
    { term: "SCA (Shot-Creating Actions)", definition: "The last offensive actions (passes, dribbles, fouls drawn) that directly led to a shot. Highlights creators, not just shooters." },
    { term: "SCA xT", definition: "The expected-threat value of shot-creating actions — how much danger the creator generated with the pass or carry before the shot." },
    { term: "xA (Expected Assists)", definition: "The xG of the shot that followed a pass — how likely the pass was to become an assist regardless of the finish." },
    { term: "On target (SOT)", definition: "Shots that would enter the goal without intervention — saved or scored. Blocked shots don't count." },
    { term: "Woodwork", definition: "Shots that struck the post or crossbar." },
  ],
  "in-possession": [
    { term: "Pass Network", definition: "Average positions of the starting XI with lines weighted by how often each pair combined. Thicker lines = more frequent passing lanes." },
    { term: "Progressive Pass", definition: "A completed pass that moves the ball significantly closer to the opponent's goal (typically ≥25% closer or into the box)." },
    { term: "xT (Expected Threat)", definition: "Value added by moving the ball into more dangerous zones via passes and carries." },
    { term: "Sub Window", definition: "A segment of the match between substitutions — the network is rebuilt per window because average positions change when players change." },
    { term: "Game State", definition: "Filter by score situation (level, leading, trailing) — teams behave differently depending on the scoreline." },
    { term: "Ball Retention", definition: "How safely a team keeps possession under pressure, typically measured in the defensive third of buildup." },
  ],
  "out-of-possession": [
    { term: "Defensive Actions", definition: "Tackles, interceptions, recoveries, clearances, and blocked passes — everything a team does to win the ball back." },
    { term: "Zone Map", definition: "The pitch split into zones (Juego de Posición grid) showing where a team's defensive work happens. Darker = more actions there." },
    { term: "Recovery", definition: "Winning a loose ball back without a direct duel — often the first sign of an effective counter-press." },
    { term: "Interception", definition: "Cutting out an opponent's pass by reading the play." },
    { term: "Defensive Third", definition: "The third of the pitch nearest a team's own goal (x < 35 on a 105m pitch)." },
  ],
  "duels-transitions": [
    { term: "Ground Duel", definition: "A one-on-one contest on the ground: take-ons, tackles, challenges, and fouls won." },
    { term: "Aerial Duel", definition: "A header contest between two players, marked won or lost in the event data." },
    { term: "Duel Zone Map", definition: "Zones colored by which team won more duels there — a picture of physical dominance across the pitch." },
    { term: "Transition", definition: "The moments right after possession changes hands. Offensive transitions = counter-attacks; defensive transitions = counter-pressing or recovering shape." },
    { term: "End Product", definition: "What the transition led to within a few events — a shot, a corner, territory gained, or possession lost again." },
  ],
  "player-analysis": [
    { term: "Heatmap", definition: "Where the player touched the ball, smoothed over the pitch. Hotter areas = more involvement." },
    { term: "Progressive Action", definition: "A pass or carry that moves the ball substantially toward the opponent's goal." },
    { term: "Possession Lost", definition: "Actions where the player gave the ball away — misplaced passes, failed take-ons, or heavy touches." },
    { term: "Defended Area", definition: "The zone containing most of the player's defensive actions — a proxy for their defensive territory." },
    { term: "Carry", definition: "Moving the ball a meaningful distance with the feet between touches or actions." },
    { term: "Ball Recovery", definition: "Regaining a loose ball for the team without needing a tackle." },
  ],
};
