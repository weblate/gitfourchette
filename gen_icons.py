def write(filename, fill='#ff00ff', char='X', round=2):
    svg = "<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16'>\n"
    svg += F"<rect rx='{round}' ry='{round}' x='0.5' y='0.5' width='15' height='15' stroke='white' stroke-width='1' fill='{fill}'/>\n"
    svg += F"<text x='8' y='12' font-weight='bold' font-size='11' font-family='sans-serif' text-anchor='middle' fill='white'>{char}</text>\n"
    svg += F"</svg>"
    print(char)
    with open(F"icons/{filename}.svg", 'w') as f:
        f.write(svg)

# https://git-scm.com/docs/git-diff#_raw_output_format

write('status_a', '#0EDF00', 'A')  # add
write('status_c', '#000000', 'C')
write('status_d', '#FE635F', 'D')  # delete
write('status_m', '#F7C342', 'M')  # modify
write('status_r', '#D18DE1', 'R')  # renamed
write('status_t', '#000000', 'T')
write('status_u', '#90a0b0', 'U')  # unmerged
write('status_x', '#ff00ff', 'X')  # unknown
write('logo',     '#00B4DF', 'G')  # not an actual status, just for the logo
