// General JavaScript functions used across multiple pages
function viewPatient(id) {
    window.location.href = `/patients/${id}`;
}

function printDocument() {
    window.print();
}

// ... other shared functions ...