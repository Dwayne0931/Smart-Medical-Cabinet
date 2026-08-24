document.addEventListener('DOMContentLoaded', function () {

    const searchInput = document.getElementById('searchInput');
    const tableRows = document.querySelectorAll('table tr:not(:first-child)');
    const noResultsMessage = document.getElementById('noResults');

    searchInput.addEventListener('input', function () {

        // Get the text entered in the search box
        const searchText = searchInput.value.toLowerCase().trim();

        let visibleRows = 0;

        // Check every row in the table
        tableRows.forEach(function (row) {

            const rowText = row.textContent.toLowerCase();

            // Show the row if it contains the search text
            if (searchText === '' || rowText.includes(searchText)) {
                row.style.display = '';
                visibleRows++;
            } else {
                row.style.display = 'none';
            }
        });

        // Show "No results" if nothing was found
        if (visibleRows === 0 && searchText !== '') {
            noResultsMessage.style.display = 'block';
        } else {
            noResultsMessage.style.display = 'none';
        }
    });
});